import sys
import os
import re
import json
from bs4 import BeautifulSoup, Tag, NavigableString

# --- Configuration ---
BIBLE_DIR = 'WEBBible' # Directory containing index.htm and chapter files
INDEX_FILE_NAME = 'index.htm'
OUTPUT_BASE_DIR = 'WEBBibleJSON' # Base directory for the structured output

# --- Verse Extraction Function (Based on previous refinements) ---
# (This function remains unchanged)
def extract_verses_from_html(html_content):
    """
    Parses HTML content of a chapter file and extracts verses.

    Args:
        html_content: String containing the HTML of the chapter.

    Returns:
        A dictionary {verse_number (int): verse_text (str)} or None if parsing fails.
    """
    verses_dict = {}
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        main_content = soup.find('div', class_='main')
        if not main_content:
             body_content = soup.find('body')
             if not body_content: return None
             main_content = body_content

        for a in main_content.find_all('a'):
            a.decompose()

        footnote_div = main_content.find('div', class_='footnote')
        copyright_div = main_content.find('div', class_='copyright')

        verse_tags = main_content.find_all('span', class_='verse')
        if not verse_tags:
             return None

        for i, verse_tag in enumerate(verse_tags):
            try:
                verse_number_str = verse_tag.get_text(strip=True)
                verse_number_int = int(verse_number_str)
            except ValueError:
                continue

            content_parts = []
            current_element = verse_tag

            while True:
                current_element = current_element.next_element

                if current_element is None: break
                if i + 1 < len(verse_tags) and current_element == verse_tags[i+1]: break
                if (footnote_div and current_element == footnote_div) or \
                   (copyright_div and current_element == copyright_div): break
                is_in_excluded_section = False
                if isinstance(current_element, (Tag, NavigableString)):
                    if footnote_div:
                        for parent in current_element.parents:
                            if parent == footnote_div: is_in_excluded_section = True; break
                    if not is_in_excluded_section and copyright_div:
                        for parent in current_element.parents:
                             if parent == copyright_div: is_in_excluded_section = True; break
                if is_in_excluded_section: break

                if isinstance(current_element, Tag):
                    if current_element.name == 'span' and current_element.get('class') == ['wj']:
                        content_parts.append(str(current_element))
                elif isinstance(current_element, NavigableString):
                    parent = current_element.parent
                    is_excluded_parent = False
                    if isinstance(parent, Tag) and parent.name == 'span':
                        parent_class = parent.get('class')
                        if parent_class and ('wj' in parent_class or 'verse' in parent_class):
                             is_excluded_parent = True
                    if not is_excluded_parent:
                        content_parts.append(str(current_element))

            full_verse_text = ''.join(content_parts).strip()
            full_verse_text = full_verse_text.replace('\xa0', ' ')
            full_verse_text = ' '.join(full_verse_text.split())

            if full_verse_text:
                 verses_dict[verse_number_int] = full_verse_text.strip()

    except Exception as e:
        print(f"Error parsing chapter content: {e}", file=sys.stderr)
        return None

    return verses_dict if verses_dict else None

# --- Main Processing Logic ---
def process_and_save_books(base_dir, output_dir):
    """
    Processes index.htm and chapter files within base_dir,
    saving each chapter's verses to a structured directory in output_dir.
    """
    index_file_path = os.path.join(base_dir, INDEX_FILE_NAME)

    if not os.path.exists(index_file_path):
        print(f"Error: Index file '{index_file_path}' not found.", file=sys.stderr)
        return False

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        print(f"Error creating base output directory '{output_dir}': {e}", file=sys.stderr)
        return False

    processed_books_count = 0
    total_chapters_saved = 0

    try:
        print(f"Reading index file: {index_file_path}")
        with open(index_file_path, 'r', encoding='utf-8') as f:
            index_soup = BeautifulSoup(f, 'html.parser')

        book_list_container = index_soup.find('div', class_='bookList')
        if not book_list_container:
             print(f"Error: Could not find '<div class=\"bookList\">' in {index_file_path}", file=sys.stderr)
             return False

        book_links = book_list_container.find_all('a')
        print(f"Found {len(book_links)} potential book links.")

        for link in book_links:
            link_class = link.get('class')
            if link_class and ('oo' in link_class or 'nn' in link_class):
                book_name = link.get_text(strip=True)
                # safe_book_name = book_name.replace(' ', '_').replace(':', '_')
                href = link.get('href')
                if not book_name or not href: continue

                match = re.match(r"([A-Z1-9]+)(\d+)\.htm$", href, re.IGNORECASE)
                if not match: continue

                base_code = match.group(1).upper()
                first_chapter_num_str = match.group(2)
                padding = len(first_chapter_num_str)
                start_chapter = int(first_chapter_num_str)

                print(f"Processing Book: {book_name}")
                book_dir_path = os.path.join(output_dir, book_name) # Path for BookName directory

                chapters_processed_for_book = 0
                chapter_num = start_chapter
                while True:
                    chapter_num_str = f"{chapter_num:0{padding}d}"
                    chapter_filename_only = f"{base_code}{chapter_num_str}.htm"
                    chapter_filepath = os.path.join(base_dir, chapter_filename_only)

                    try:
                        with open(chapter_filepath, 'r', encoding='utf-8') as chapter_file:
                            file_content = chapter_file.read()

                        verses_dict = extract_verses_from_html(file_content)

                        if verses_dict:
                             # Create Book directory only if we have data for its first chapter
                            if chapters_processed_for_book == 0:
                                try:
                                    os.makedirs(book_dir_path, exist_ok=True)
                                except OSError as e:
                                     print(f"  Error creating book directory '{book_dir_path}': {e}", file=sys.stderr)
                                     # Decide if we should stop processing the book or just skip saving
                                     break # Stop processing this book if its dir can't be made

                            # --- Simplified Path ---
                            # Define output JSON file path directly in the book directory
                            output_json_path = os.path.join(book_dir_path, f"{chapter_num}.json")

                            # Write the verses dictionary to the chapter JSON file
                            try:
                                with open(output_json_path, 'w', encoding='utf-8') as outfile:
                                    json.dump(verses_dict, outfile, indent=4, ensure_ascii=False)
                                chapters_processed_for_book += 1
                            except IOError as e:
                                print(f"  Error writing JSON file '{output_json_path}': {e}", file=sys.stderr)
                            except Exception as e:
                                print(f"  Unexpected error writing JSON for chapter {chapter_num} of {book_name}: {e}", file=sys.stderr)

                        chapter_num += 1

                    except FileNotFoundError:
                        break # End of chapters for this book
                    except Exception as e:
                        print(f"  Error processing chapter file '{chapter_filepath}': {e}", file=sys.stderr)
                        break # Stop processing this book on other errors

                if chapters_processed_for_book > 0:
                    processed_books_count += 1
                    total_chapters_saved += chapters_processed_for_book
                    print(f"Finished processing {book_name}, saved {chapters_processed_for_book} chapters.")

    except Exception as e:
        print(f"An error occurred during index processing: {e}", file=sys.stderr)
        return False

    print(f"\nFinished processing. Saved {total_chapters_saved} chapters across {processed_books_count} books to '{output_dir}'.")
    return True

# --- Main Execution ---
if __name__ == "__main__":
    success = process_and_save_books(BIBLE_DIR, OUTPUT_BASE_DIR)

    if success:
        print("\nProcessing complete.")
    else:
        print("\nProcessing failed or completed with errors.")