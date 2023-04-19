import re
import sys
import os
import gzip
import json
from datetime import datetime

import numpy as np
import pandas as pd
from fastparquet import write as parquet_write

import util

TRACKED_TAGS = (
    "created_by",
    "comment",
    "imagery_used",
    "locale",
    "source",
    "host",
    "changesets_count",
    "hashtags",
    "StreetComplete",
    "version",
    "bot",
)

# change some streetcomplete quest type tags that changed their name over the time to the newest name
# https://github.com/streetcomplete/StreetComplete/issues/1749#issuecomment-593450124
sc_quest_type_tag_changes = {
    "AddAccessibleForPedestrians": "AddProhibitedForPedestrians",
    "AddWheelChairAccessPublicTransport": "AddWheelchairAccessPublicTransport",
    "AddWheelChairAccessToilets": "AddWheelchairAccessPublicTransport",
    "AddSidewalks": "AddSidewalk",
}


def get_tags(tags_str):
    tags = {}
    if len(tags_str) > 0:
        for key_value in tags_str.split(","):
            key, value = key_value.split("=")
            tags[key] = value
    return tags


def debug_regex(regex, text):
    sub = re.sub(regex, "", text)
    sys.stderr.write(f'{text != sub}: "{text}"  =>  "{sub}"\n')


class IndexDict:
    def __init__(self, name):
        self.counter = -1
        self.dict = {}
        self.name = name

    def add(self, key):
        if key not in self.dict:
            self.counter += 1
            self.dict[key] = self.counter
        index = self.dict[key]
        return index

    def add_keys(self, keys):
        if len(keys) == 0:
            return ()
        else:
            return list(self.add(key) for key in keys)

    def save(self, save_dir):
        revesed_dict = {value: key for key, value in self.dict.items()}
        filepath = os.path.join(save_dir, f"index_to_tag_{self.name}.txt")
        with open(filepath, "w", encoding="UTF-8") as f:
            # f.write(f"\n")
            for line in [revesed_dict[key] for key in sorted(revesed_dict.keys())]:
                f.write(f"{line}\n")


def get_year_and_month_to_index():
    first_year = 2005
    first_month = 4
    now = datetime.now()
    last_year = now.year
    last_month = now.month - 1
    years = [str(year) for year in range(first_year, last_year + 1)]
    year_to_index = {year: i for i, year in enumerate(years)}
    months = []
    for year in years:
        months.extend(f"{year}-{month:02d}" for month in range(1, 13))
    months = months[first_month - 1 : -12 + last_month]
    month_to_index = {month: i for i, month in enumerate(months)}
    return years, year_to_index, months, month_to_index


def get_pos(data):
    if len(data[7][1:]) > 0:
        min_x = float(data[7][1:])
        max_x = float(data[9][1:])
        pos_x = round(((min_x + max_x) / 2) - 180) % 360

        min_y = float(data[8][1:])
        max_y = float(data[10][1:])
        pos_y = round(((min_y + max_y) / 2) + 90) % 180
        return pos_x, pos_y
    else:
        return -1, -1


def get_created_by_and_sc_quest_type(tags, index_dicts, replace_rules):
    if "created_by" in tags and len(tags["created_by"]) > 0:
        created_by = tags["created_by"].replace("%20%", " ").replace("%2c%", ",")
        created_by = replace_with_rules(created_by, replace_rules["created_by"])

        created_by_index = index_dicts["created_by"].add(created_by)

        if created_by == "StreetComplete" and "StreetComplete:quest_type" in tags:
            sc_quest_type_tag = tags["StreetComplete:quest_type"]
            sc_quest_type_tag = sc_quest_type_tag_changes.get(sc_quest_type_tag, sc_quest_type_tag)
            sc_quest_type_index = index_dicts["streetcomplete_quest_type"].add(sc_quest_type_tag)
            return created_by_index, sc_quest_type_index
        else:
            return created_by_index, 65535
    else:
        return 4_294_967_295, 65535


def get_imagery(tags, index_dicts, replace_rules):
    if "imagery_used" in tags and len(tags["imagery_used"]) > 0:
        imagery_list = [
            key for key in tags["imagery_used"].replace("%20%", " ").replace("%2c%", ",").split(";") if len(key) > 0
        ]
        for i in range(len(imagery_list)):
            if imagery_list[i][0] == " ":
                imagery_list[i] = imagery_list[i][1:]
            imagery_list[i] = replace_with_rules(imagery_list[i], replace_rules["imagery"])

        return index_dicts["imagery"].add_keys(imagery_list)
    else:
        return ()


def add_hashtags(tags, index_dicts):
    if "hashtags" in tags:
        return index_dicts["hashtag"].add_keys(tags["hashtags"].lower().split(";"))
    else:
        return ()


def add_source(tags, index_dicts, replace_rules):
    if "source" in tags and len(tags["source"]) > 0:
        source_list = [
            key for key in tags["source"].replace("%20%", " ").replace("%2c%", ",").split(";") if len(key) > 0
        ]
        # there are some source tags that are seperated with ",". Maybe split "," if there is no ";" present.
        for i in range(len(source_list)):
            if source_list[i][0] == " ":
                source_list[i] = source_list[i][1:]
            source_list[i] = replace_with_rules(source_list[i], replace_rules["source"])
            source_list[i] = source_list[i][:120]

        return index_dicts["source"].add_keys(source_list)
    else:
        return ()


def add_all_tags(tags, index_dicts):
    return index_dicts["all_tags"].add_keys(
        [tag_name.split(":")[0] for tag_name in tags.keys() if tag_name not in TRACKED_TAGS]
    )


# def add_bot_usage(tags):
#     if "bot" in tags and tags["bot"] == "yes":
#         return True
#     else:
#         return False


def create_replace_rules():
    replace_rules = {}
    for tag_name, file_name in [
        ("created_by", "replace_rules_created_by.json"),
        ("imagery", "replace_rules_imagery_and_source.json"),
        ("source", "replace_rules_imagery_and_source.json"),
    ]:
        name_to_tags_and_link = util.load_json(os.path.join("src", file_name))
        tag_to_name = {}
        starts_with_list = []
        ends_with_list = []
        for name, name_infos in name_to_tags_and_link.items():
            if "aliases" in name_infos:
                for alias in name_infos["aliases"]:
                    tag_to_name[alias] = name
            if "starts_with" in name_infos:
                for starts_with in name_infos["starts_with"]:
                    starts_with_list.append((len(starts_with), starts_with, name))
            if "ends_with" in name_infos:
                for ends_with in name_infos["ends_with"]:
                    ends_with_list.append((len(ends_with), ends_with, name))

        replace_rules[tag_name] = {
            "tag_to_name": tag_to_name,
            "starts_with_list": starts_with_list,
            "ends_with_list": ends_with_list,
        }
    return replace_rules


def replace_with_rules(tag, replace_rules):
    if tag in replace_rules["tag_to_name"]:
        return replace_rules["tag_to_name"][tag]

    for compare_str_length, compare_str, replace_str in replace_rules["starts_with_list"]:
        if tag[:compare_str_length] == compare_str:
            return replace_str

    for compare_str_length, compare_str, replace_str in replace_rules["ends_with_list"]:
        if tag[-compare_str_length:] == compare_str:
            return replace_str

    return tag


def save_data(parquet_save_dir, file_counter, batch_size, data_dict):
    general = {
        "changeset_index": np.array(data_dict["changeset_index"], dtype=np.uint32),
        "year_index": np.array(data_dict["year_index"], dtype=np.uint8),
        "month_index": np.array(data_dict["month_index"], dtype=np.uint16),
        "edits": np.array(data_dict["edits"], dtype=np.uint32),
        "user_index": np.array(data_dict["user_index"], dtype=np.uint32),
        "pos_x": np.array(data_dict["pos_x"], dtype=np.int16),
        "pos_y": np.array(data_dict["pos_y"], dtype=np.int16),
        "created_by": np.array(data_dict["created_by"], dtype=np.uint32),
        "sc_quest_type": np.array(data_dict["sc_quest_type"], dtype=np.uint16),
        "bot": np.array(data_dict["bot"], dtype=np.bool_),
        "comment": np.array(data_dict["comment"], dtype=np.bool_),
        "local": np.array(data_dict["local"], dtype=np.bool_),
        "host": np.array(data_dict["host"], dtype=np.bool_),
        "changeset_count": np.array(data_dict["changeset_count"], dtype=np.bool_),
        "version": np.array(data_dict["changeset_count"], dtype=np.bool_),
    }
    parquet_write(
        os.path.join(parquet_save_dir, f"general_{file_counter}.parquet"),
        pd.DataFrame.from_dict(data=general),
        compression="GZIP",
    )

    for tag_name in ("imagery", "hashtag", "source", "all_tags"):
        changeset_index = np.array(data_dict[f"{tag_name}_changeset_index"], dtype=np.uint32)
        changeset_index_with_offset = changeset_index - (batch_size * file_counter)
        tag_dict = {
            "changeset_index": changeset_index_with_offset,
            "year_index": general["year_index"][changeset_index_with_offset],
            "month_index": general["month_index"][changeset_index_with_offset],
            "edits": general["edits"][changeset_index_with_offset],
            "user_index": general["user_index"][changeset_index_with_offset],
            "pos_x": general["pos_x"][changeset_index_with_offset],
            "pos_y": general["pos_y"][changeset_index_with_offset],
            "created_by": general["created_by"][changeset_index_with_offset],
            tag_name: np.array(data_dict[tag_name], dtype=np.uint32),
        }
        parquet_write(
            os.path.join(parquet_save_dir, f"{tag_name}_{file_counter}.parquet"),
            pd.DataFrame.from_dict(data=tag_dict),
            compression="GZIP",
        )


def init_data_dict():
    # TODO: do this more efficiant with numpy arrays?
    data_dict = {
        "changeset_index": [],
        "year_index": [],
        "month_index": [],
        "edits": [],
        "user_index": [],
        "pos_x": [],
        "pos_y": [],
        "created_by": [],
        "sc_quest_type": [],
        "bot": [],
        "comment": [],
        "local": [],
        "host": [],
        "changeset_count": [],
        "version": [],
    }
    for tag_name in ("imagery", "hashtag", "source", "all_tags"):
        data_dict[f"{tag_name}_changeset_index"] = []
        data_dict[tag_name] = []
    return data_dict


def main():
    save_dir = sys.argv[1]
    os.makedirs(save_dir, exist_ok=True)
    years, year_to_index, months, month_to_index = get_year_and_month_to_index()

    with open(os.path.join(save_dir, "months.txt"), "w", encoding="UTF-8") as f:
        f.writelines("\n".join(months))
        f.writelines("\n")

    with open(os.path.join(save_dir, "years.txt"), "w", encoding="UTF-8") as f:
        f.writelines("\n".join(years))
        f.writelines("\n")

    index_dicts = {
        "user_name": IndexDict("user_name"),
        "created_by": IndexDict("created_by"),
        "streetcomplete_quest_type": IndexDict("streetcomplete_quest_type"),
        "imagery": IndexDict("imagery"),
        "hashtag": IndexDict("hashtag"),
        "source": IndexDict("source"),
        "all_tags": IndexDict("all_tags"),
    }

    replace_rules = create_replace_rules()

    parquet_save_dir = os.path.join(save_dir, "changeset_data")
    os.makedirs(parquet_save_dir, exist_ok=True)

    batch_size = 5_000_000
    file_counter = 0
    for i, osmium_line in enumerate(sys.stdin):
        if i % batch_size == 0:
            if i > 0:
                save_data(parquet_save_dir, file_counter, batch_size, data_dict)
                file_counter += 1
            data_dict = init_data_dict()

        data = osmium_line.split(" ")
        if data[2][1:8] not in month_to_index:
            continue

        data_dict["changeset_index"].append(i)
        data_dict["year_index"].append(year_to_index[data[2][1:5]])
        data_dict["month_index"].append(month_to_index[data[2][1:8]])
        data_dict["edits"].append(int(data[1][1:]))
        data_dict["user_index"].append(int(index_dicts["user_name"].add(data[6][1:])))

        pos_x, pos_y = get_pos(data)
        data_dict["pos_x"].append(pos_x)
        data_dict["pos_y"].append(pos_y)

        tags = get_tags(data[11][1:-1])
        created_by, sc_quest_type = get_created_by_and_sc_quest_type(tags, index_dicts, replace_rules)
        data_dict["created_by"].append(created_by)
        data_dict["sc_quest_type"].append(sc_quest_type)
        data_dict["bot"].append("bot" in tags and tags["bot"] == "yes")
        data_dict["comment"].append("comment" in tags)
        data_dict["local"].append("local" in tags)
        data_dict["host"].append("host" in tags)
        data_dict["changeset_count"].append("changeset_count" in tags)
        data_dict["version"].append("version" in tags)

        for index in get_imagery(tags, index_dicts, replace_rules):
            data_dict["imagery_changeset_index"].append(i)
            data_dict["imagery"].append(index)

        for index in add_hashtags(tags, index_dicts):
            data_dict["hashtag_changeset_index"].append(i)
            data_dict["hashtag"].append(index)

        for index in add_source(tags, index_dicts, replace_rules):
            data_dict["source_changeset_index"].append(i)
            data_dict["source"].append(index)

        for index in add_all_tags(tags, index_dicts):
            data_dict["all_tags_changeset_index"].append(i)
            data_dict["all_tags"].append(index)

    save_data(parquet_save_dir, file_counter, batch_size, data_dict)

    for index_dict in index_dicts.values():
        index_dict.save(save_dir)


if __name__ == "__main__":
    main()
