import argparse
import json
import os
import uuid
from pathlib import Path


def convert_notebook_to_html(notebook_path: str, all_notebooks=None):
    """Convert a Jupyter notebook to a basic HTML page"""

    with open(notebook_path, encoding="utf-8") as f:
        notebook = json.load(f)

    notebook_name = Path(notebook_path).stem
    html_content = generate_html(notebook, notebook_name, all_notebooks)
    output_path = os.path.join("stats", f"{notebook_name}.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Converted {notebook_path} to {output_path}")
    return output_path


def extract_code_label(source_text, is_first_code_cell=False):
    """Extract label for code block"""
    if is_first_code_cell:
        return "Imports and Default Layout"
    return "code"


def extract_title_from_notebook(notebook):
    """Extract title from the first markdown cell"""
    cells = notebook.get("cells", [])

    for cell in cells:
        if cell.get("cell_type") == "markdown":
            source = cell.get("source", [])
            if isinstance(source, list):
                source_text = "".join(source)
            else:
                source_text = str(source)

            # Look for the first header
            lines = source_text.strip().split("\n")
            for line in lines:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()

            # If no header found, use first non-empty line
            for line in lines:
                line = line.strip()
                if line:
                    return line

    return "Converted Notebook"


def generate_html(notebook, notebook_name="", all_notebooks=None):
    """Generate basic HTML from notebook content"""

    # Extract title from notebook
    title = extract_title_from_notebook(notebook)

    # Generate navigation links for all pages
    nav_links = ""
    if all_notebooks:
        link_items = []
        for nb_path in sorted(all_notebooks):
            nb_name = Path(nb_path).stem
            # Remove number prefixes like "01_", "02_", etc.
            display_name = nb_name
            if "_" in display_name and display_name.split("_")[0].isdigit():
                display_name = "_".join(display_name.split("_")[1:])
            display_name = display_name.replace("_", " ").title()

            if nb_name == notebook_name:  # Current page should be marked as active
                link_items.append(f'<a href="{nb_name}.html" class="nav-link active">{display_name}</a>')
            else:
                link_items.append(f'<a href="{nb_name}.html" class="nav-link">{display_name}</a>')

        if link_items:
            links_html = "\n                ".join(link_items)
            nav_links = (
                """
        <div class="page-navigation">
            <div class="nav-links-container">
                """
                + links_html
                + """
            </div>
        </div>"""
            )

    # Generate header HTML
    header_html = (
        """<header class='header'>
        """
        + nav_links
        + """
        <nav>
            <a href="https://github.com/piebro/openstreetmap-statistics">About this project</a>
            <a href="https://piebro.github.io?ref=piebro.github.io/openstreetmap-statistics/">About me</a>
        </nav>
    </header>"""
    )

    # Generate footer HTML
    footer_nav_links = ""
    if all_notebooks:
        footer_link_items = []
        for nb_path in sorted(all_notebooks):
            nb_name = Path(nb_path).stem
            # Remove number prefixes like "01_", "02_", etc.
            display_name = nb_name
            if "_" in display_name and display_name.split("_")[0].isdigit():
                display_name = "_".join(display_name.split("_")[1:])
            display_name = display_name.replace("_", " ").title()

            if nb_name == notebook_name:  # Current page should be marked as active
                footer_link_items.append(f'<a href="{nb_name}.html" class="nav-link active">{display_name}</a>')
            else:
                footer_link_items.append(f'<a href="{nb_name}.html" class="nav-link">{display_name}</a>')

        if footer_link_items:
            footer_links_html = " | ".join(footer_link_items)
            footer_nav_links = f'<p class="footer-navigation">{footer_links_html}</p>'

    footer_html = f"<footer class='footer'>{footer_nav_links}</footer>"

    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="../notebooks/notebook.css">
    <script src="../notebooks/notebook.js"></script>
    <script src="https://cdn.plot.ly/plotly-3.0.1.min.js" charset="utf-8"></script>

    <link rel="stylesheet" href="notebook_styles.css">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism.min.css" rel="stylesheet" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-core.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>
    <script defer data-domain="piebro.github.io/openstreetmap-statistics" src="https://plausible.io/js/script.js"></script>
</head>
<body>
    {header}
    {content}
    {footer}
    <script>
        function toggleCode(button) {{
            const content = button.nextElementSibling;
            const isExpanded = content.classList.contains('expanded');
            
            if (isExpanded) {{
                content.classList.remove('expanded');
                button.classList.remove('expanded');
            }} else {{
                content.classList.add('expanded');
                button.classList.add('expanded');
            }}
        }}
    </script>
</body>
</html>"""

    content_parts = []
    first_code_cell = True

    # Process each cell
    for cell in notebook.get("cells", []):
        cell_type = cell.get("cell_type", "")
        source = cell.get("source", [])

        # Join source lines
        if isinstance(source, list):
            source_text = "".join(source)
        else:
            source_text = str(source)

        if cell_type == "markdown":
            # Simple markdown processing (just convert headers)
            processed_content = process_simple_markdown(source_text)
            content_parts.append(f'<div class="cell markdown-cell">{processed_content}</div>')

        elif cell_type == "code":
            # Skip empty code cells
            if not source_text.strip():
                continue

            # Skip the first code cell (Imports and Default Layout)
            if first_code_cell:
                first_code_cell = False
                continue

            # Extract label for the code block
            code_label = extract_code_label(source_text, first_code_cell)
            code_id = f"code-{uuid.uuid4().hex[:8]}"

            code_html = f'''<div class="code">
                <div class="code-toggle" onclick="toggleCode(this)">{escape_html(code_label)}</div>
                <div class="code-content" id="{code_id}">
                    <pre><code class="language-python">{escape_html(source_text)}</code></pre>
                </div>
            </div>'''

            # Add outputs if they exist
            outputs = cell.get("outputs", [])
            output_html = ""
            if outputs:
                for output in outputs:
                    output_html += process_output(output)

            content_parts.append(f'<div class="cell code-cell">{code_html}{output_html}</div>')

    return html_template.format(title=title, header=header_html, content="\n".join(content_parts), footer=footer_html)


def process_output(output):
    """Process notebook cell output and return HTML"""
    output_html = ""

    # Handle different output types
    if output.get("output_type") == "display_data" and "data" in output:
        data = output["data"]

        # Handle Plotly plots
        if "application/vnd.plotly.v1+json" in data:
            plotly_data = data["application/vnd.plotly.v1+json"]
            plot_id = f"plotly-div-{uuid.uuid4().hex[:8]}"

            # Extract the actual plot data and layout
            plot_data = plotly_data.get("data", [])
            plot_layout = plotly_data.get("layout", {})
            plot_config = plotly_data.get("config", {})

            # Create a div for the plot and JavaScript to render it
            # Configure for responsive behavior
            plot_config = plot_config or {}
            plot_config.update({"responsive": True, "displayModeBar": True, "displaylogo": False})

            output_html += f'''
<div id="{plot_id}" class="plotly-output"></div>
<script>
    Plotly.newPlot('{plot_id}', {json.dumps(plot_data)}, {json.dumps(plot_layout)}, {json.dumps(plot_config)});
</script>
'''

        # Handle HTML tables (pandas DataFrames)
        elif "text/html" in data:
            html_data = data["text/html"]
            if isinstance(html_data, list):
                html_data = "".join(html_data)

            # Check if it's a pandas DataFrame table
            if "<table" in html_data and "dataframe" in html_data:
                table_id = f"table-{uuid.uuid4().hex[:8]}"
                output_html += f'<div class="table-output" id="{table_id}">{html_data}</div>'
                output_html += f"""
<script>
    // Format numbers in table with commas
    document.addEventListener('DOMContentLoaded', function() {{
        const table = document.querySelector('#{table_id} table');
        if (table) {{
            const cells = table.querySelectorAll('td:not(:first-child)');
            cells.forEach(cell => {{
                const text = cell.textContent.trim();
                if (/^\\d+$/.test(text)) {{
                    const number = parseInt(text);
                    cell.textContent = number.toLocaleString();
                }}
            }});
        }}
    }});
</script>
"""
            else:
                output_html += f'<div class="output">{html_data}</div>'

    # Handle execute_result outputs (like DataFrame displays)
    elif output.get("output_type") == "execute_result" and "data" in output:
        print("execute_result")
        data = output["data"]

        # Handle HTML tables (pandas DataFrames)
        if "text/html" in data:
            html_data = data["text/html"]
            if isinstance(html_data, list):
                html_data = "".join(html_data)

            # Check if it's a pandas DataFrame table
            if "<table" in html_data and "dataframe" in html_data:
                table_id = f"table-{uuid.uuid4().hex[:8]}"
                output_html += f'<div class="table-output" id="{table_id}">{html_data}</div>'
                output_html += f"""
<script>
    // Format numbers in table with commas
    document.addEventListener('DOMContentLoaded', function() {{
        const table = document.querySelector('#{table_id} table');
        if (table) {{
            const cells = table.querySelectorAll('td:not(:first-child)');
            cells.forEach(cell => {{
                const text = cell.textContent.trim();
                if (/^\\d+$/.test(text)) {{
                    const number = parseInt(text);
                    cell.textContent = number.toLocaleString();
                }}
            }});
        }}
    }});
</script>
"""
            else:
                output_html += f'<div class="output">{html_data}</div>'

        # Handle text output as fallback
        elif "text/plain" in data:
            text_data = data["text/plain"]
            if isinstance(text_data, list):
                text_data = "".join(text_data)

            # Skip widget-related text outputs
            if not ("Progress(" in text_data or "Widget(" in text_data or "Layout(" in text_data):
                output_html += f'<div class="output">{escape_html(text_data)}</div>'

    # Handle text output from stream
    elif "text" in output:
        print("text")
        output_text = "".join(output["text"]) if isinstance(output["text"], list) else output["text"]
        output_html += f'<div class="output">{escape_html(output_text)}</div>'

    return output_html


def process_simple_markdown(text):
    """Basic markdown processing for headers and links"""
    lines = text.split("\n")
    processed_lines = []

    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            processed_lines.append(f"<h1>{process_markdown_links(line[2:])}</h1>")
        elif line.startswith("## "):
            processed_lines.append(f"<h2>{process_markdown_links(line[3:])}</h2>")
        elif line.startswith("### "):
            processed_lines.append(f"<h3>{process_markdown_links(line[4:])}</h3>")
        elif line:
            processed_lines.append(f"<p>{process_markdown_links(line)}</p>")

    return "\n".join(processed_lines)


def process_markdown_links(text):
    """Convert markdown links to HTML links"""
    import re

    # Pattern to match markdown links: [text](url)
    link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

    def replace_link(match):
        link_text = escape_html(match.group(1))
        link_url = escape_html(match.group(2))
        return f'<a href="{link_url}">{link_text}</a>'

    # Replace markdown links with HTML links
    result = re.sub(link_pattern, replace_link, text)

    # Escape remaining HTML characters (but not the links we just created)
    result = escape_html_except_links(result)

    return result


def escape_html_except_links(text):
    """Escape HTML characters but preserve link tags"""
    import re

    # Find all link tags to preserve them
    link_pattern = r'<a href="[^"]*">[^<]*</a>'
    links = re.findall(link_pattern, text)

    # Replace links with placeholders
    placeholder_text = text
    for i, link in enumerate(links):
        placeholder = f"__LINK_PLACEHOLDER_{i}__"
        placeholder_text = placeholder_text.replace(link, placeholder, 1)

    # Escape HTML in the text with placeholders
    escaped_text = escape_html(placeholder_text)

    # Restore the links
    for i, link in enumerate(links):
        placeholder = f"__LINK_PLACEHOLDER_{i}__"
        escaped_text = escaped_text.replace(placeholder, link)

    return escaped_text


def escape_html(text):
    """Escape HTML special characters"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def generate_index_html(output_dir: str = "stats"):
    """Generate an index.html file listing all available statistics"""

    # Find all HTML files in the output directory (excluding index.html)
    html_files = []
    if os.path.exists(output_dir):
        for file in os.listdir(output_dir):
            if file.endswith(".html") and file != "index.html":
                html_files.append(file)

    # Sort files alphabetically
    html_files.sort()

    # Generate navigation links
    nav_links = []
    for html_file in html_files:
        # Create a display name from filename
        display_name = html_file.replace(".html", "").replace("_", " ").title()
        nav_links.append(f'            <li><a href="{html_file}">{display_name}</a></li>')

    # Generate header HTML
    header_html = """<header class='header'>
        <nav>
            <a href="https://github.com/piebro/openstreetmap-statistics/">GitHub</a>
            <a href="https://github.com/piebro/openstreetmap-statistics/blob/master/README.md">About</a>
        </nav>
    </header>"""

    # Generate footer HTML
    footer_html = """<footer class='footer'>
        <p>&copy; 2025 OpenStreetMap Statistics. Data from OpenStreetMap contributors.</p>
        <p><a href="https://github.com/piebro/openstreetmap-statistics/">View on GitHub</a></p>
    </footer>"""

    # Generate index content
    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=1024, initial-scale=1.0, user-scalable=yes">
    <title>OpenStreetMap Statistics</title>
    <link rel="stylesheet" href="notebook_styles.css">
    <script defer data-domain="piebro.github.io/openstreetmap-statistics" src="https://plausible.io/js/script.js"></script>
</head>
<body>
    {header_html}
    
    <div class="cell markdown-cell">
        <h1>OpenStreetMap Statistics</h1>
        <p>Explore various statistics and analyses of OpenStreetMap data.</p>
    </div>
    
    <div class="cell markdown-cell">
        <h2>Available Statistics</h2>
        <ul>
{chr(10).join(nav_links)}
        </ul>
    </div>
    
    {footer_html}
</body>
</html>"""

    # Write index.html file
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"Generated index file at {index_path}")
    return index_path


def main():
    """Main CLI function"""
    parser = argparse.ArgumentParser(description="Convert Jupyter notebooks to HTML")
    parser.add_argument("--notebook", help="Path to a specific Jupyter notebook file (optional)")
    parser.add_argument(
        "--directory", "-d", default="notebooks", help="Directory to search for notebooks (default: notebooks)"
    )

    args = parser.parse_args()

    # If a specific notebook is provided, convert only that one
    if args.notebook:
        if not os.path.exists(args.notebook):
            print(f"Error: Notebook file '{args.notebook}' not found")
            return 1

        try:
            convert_notebook_to_html(args.notebook)
            return 0
        except Exception as e:
            print(f"Error converting notebook: {e}")
            return 1

    # Otherwise, find and convert all notebooks
    if not os.path.exists(args.directory):
        print(f"Error: Directory '{args.directory}' not found")
        return 1

    # Find all .ipynb files in the directory and subdirectories
    notebook_files = []
    for root, dirs, files in os.walk(args.directory):
        for file in files:
            if file.endswith(".ipynb"):
                notebook_files.append(os.path.join(root, file))

    if not notebook_files:
        print(f"No notebook files found in '{args.directory}'")
        return 0

    print(f"Found {len(notebook_files)} notebook file(s)")

    # Convert each notebook
    for notebook_path in sorted(notebook_files):
        try:
            convert_notebook_to_html(notebook_path, notebook_files)
        except Exception as e:
            print(f"Error converting {notebook_path}: {e}")

    return 0


if __name__ == "__main__":
    exit(main())
