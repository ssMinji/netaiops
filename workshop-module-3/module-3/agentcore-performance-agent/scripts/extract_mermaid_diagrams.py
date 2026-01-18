#!/usr/bin/env python3
"""
Script to extract Mermaid diagrams from the flow diagram markdown file
and save them as individual .mmd files for conversion to images.
"""

import os
import re
import sys

def extract_mermaid_diagrams(markdown_file_path, output_dir):
    """Extract all Mermaid diagrams from a markdown file."""
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Read the markdown file
    with open(markdown_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all mermaid code blocks
    mermaid_pattern = r'```mermaid\n(.*?)\n```'
    matches = re.findall(mermaid_pattern, content, re.DOTALL)
    
    if not matches:
        print("No Mermaid diagrams found in the file.")
        return []
    
    diagram_files = []
    
    # Extract diagram names from the context
    sections = content.split('###')
    diagram_names = []
    
    for section in sections:
        if '```mermaid' in section:
            # Extract the section title
            lines = section.strip().split('\n')
            if lines:
                title = lines[0].strip()
                # Clean up the title for filename
                clean_title = re.sub(r'[^\w\s-]', '', title).strip()
                clean_title = re.sub(r'[-\s]+', '_', clean_title)
                diagram_names.append(clean_title)
    
    # If we don't have enough names, generate generic ones
    while len(diagram_names) < len(matches):
        diagram_names.append(f"diagram_{len(diagram_names) + 1}")
    
    # Save each diagram to a separate file
    for i, (diagram_content, name) in enumerate(zip(matches, diagram_names)):
        filename = f"{i+1:02d}_{name}.mmd"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(diagram_content.strip())
        
        diagram_files.append(filepath)
        print(f"Extracted diagram: {filename}")
    
    return diagram_files

def create_conversion_script(diagram_files, output_dir):
    """Create a shell script to convert all .mmd files to PNG images."""
    
    script_content = """#!/bin/bash
# Script to convert Mermaid diagrams to PNG images
# Requires: npm install -g @mermaid-js/mermaid-cli

set -e

echo "Converting Mermaid diagrams to PNG images..."

# Check if mmdc is available
if ! command -v mmdc &> /dev/null; then
    echo "Error: mmdc (Mermaid CLI) is not installed."
    echo "Please install it with: npm install -g @mermaid-js/mermaid-cli"
    exit 1
fi

"""
    
    for diagram_file in diagram_files:
        filename = os.path.basename(diagram_file)
        name_without_ext = os.path.splitext(filename)[0]
        png_filename = f"{name_without_ext}.png"
        
        script_content += f"""
echo "Converting {filename} to {png_filename}..."
mmdc -i "{diagram_file}" -o "{os.path.join(output_dir, png_filename)}" -t dark -b transparent
"""
    
    script_content += """
echo "All diagrams converted successfully!"
echo "Images saved in: """ + output_dir + """"
"""
    
    script_path = os.path.join(os.path.dirname(output_dir), "convert_diagrams.sh")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    # Make the script executable
    os.chmod(script_path, 0o755)
    
    print(f"Created conversion script: {script_path}")
    return script_path

def main():
    # Define paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    markdown_file = os.path.join(project_root, "prerequisite", "lambda-performance", "PERFORMANCE_TOOLS_FLOW_DIAGRAM.md")
    output_dir = os.path.join(project_root, "images", "flow_diagrams")
    
    print(f"Extracting Mermaid diagrams from: {markdown_file}")
    print(f"Output directory: {output_dir}")
    
    # Check if the markdown file exists
    if not os.path.exists(markdown_file):
        print(f"Error: Markdown file not found: {markdown_file}")
        sys.exit(1)
    
    # Extract diagrams
    diagram_files = extract_mermaid_diagrams(markdown_file, output_dir)
    
    if diagram_files:
        print(f"\nExtracted {len(diagram_files)} Mermaid diagrams.")
        
        # Create conversion script
        script_path = create_conversion_script(diagram_files, output_dir)
        
        print(f"\nTo convert diagrams to images, run:")
        print(f"  {script_path}")
        print("\nOr manually convert each diagram with:")
        print("  mmdc -i diagram.mmd -o diagram.png -t dark -b transparent")
        
    else:
        print("No diagrams were extracted.")

if __name__ == "__main__":
    main()
