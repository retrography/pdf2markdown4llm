from pdf2markdown4llm import PDF2Markdown4LLM
converter = PDF2Markdown4LLM(remove_headers=False, table_header="### Table")
md_content = converter.convert(r"pdf2markdown4llm\tests\SystemConfigurationandTroubleshootingManual.pdf")
with open(r"pdf2markdown4llm\tests\SystemConfigurationandTroubleshootingManual.md", "r", encoding="utf-8") as md_file:
    expected_md_content = md_file.read()
    
assert md_content == expected_md_content, "Markdown content does not match the expected content."
    