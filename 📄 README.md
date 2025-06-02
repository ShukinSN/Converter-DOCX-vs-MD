DOCX to Markdown Converter Pro

Overview

This is a Python-based application for converting DOCX files to Markdown format. It features a modern GUI built with PyQt5, supports batch processing, image handling, and table of contents generation.

Features





Convert multiple DOCX files to Markdown with customizable settings.



Support for extracting and converting images (including EMF to PNG).



Generate table of contents with anchor links.



Preview Markdown and HTML output.



Dark theme interface for better user experience.

Requirements





Python 3.6+



Pandoc (version 2.14 or higher)



Required Python packages:

pip install pypandoc markdown bs4 PyQt5 wand

Installation





Install Pandoc from https://pandoc.org/installing.html.



Install Python dependencies:

pip install -r requirements.txt



Clone the repository and navigate to the project directory.

Usage





Run the application:

python main.py



Add DOCX files or folders using the GUI.



Select an output folder and configure conversion settings (e.g., generate TOC, overwrite files).



Click "Start Conversion" to process the files.



View logs and preview converted files.

Project Structure





main.py: Entry point of the application.



src/converter/: Contains conversion logic (thread.py, utils.py).



src/dependencies/: Dependency checking (checker.py).



src/gui/: GUI components (main_window.py, palette.py, preview_window.py).

Notes





Ensure Pandoc is installed and accessible in your system PATH.



The application supports .docx files and processes images in .png, .jpg, .jpeg, .gif, and .emf formats.



Logs are displayed in the GUI, and errors are reported via message boxes.

License

MIT License