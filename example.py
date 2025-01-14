from pdf2markdown4llm import PDF2Markdown4LLM


def progress_callback(progress): 
    """Callback function to handle progress"""
    print(f"Phase: {progress.phase.value}, Page {progress.current_page}/{progress.total_pages}, Progress: {progress.percentage:.1f}%, Message: {progress.message}")


# Initialize converter
converter = PDF2Markdown4LLM(remove_headers=False, skip_empty_tables=True, table_header="### Table", progress_callback=progress_callback)

# Convert PDF to Markdown
markdown_content = converter.convert("input.pdf")

# Save to file
with open("output.md", "w", encoding="utf-8") as md_file:
    md_file.write(markdown_content)
