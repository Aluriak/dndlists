"""Automatic parsing and translation of dndspeak.com lists"""
import os
import sys
import json
import html
import glob
import argparse
import requests
import textwrap

import deepl_api


URL_PREFIX = 'https://www.dndspeak.com/'


def parse_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('targets', type=str, nargs='*', help='webpages to extract')
    parser.add_argument('--translate', '-d', action='store_true', help="perform the deepl calls")
    parser.add_argument('--translate-to', type=str, default='FR', help="target language for translations")
    parser.add_argument('--width', type=int, default=130, help="line width in rendered files")

    return parser.parse_args()


def get_url(url:str) -> str:
    r = requests.get(url)
    return html.unescape(r.text)


def translated(text:str, target_language:str) -> str:
    deepl = deepl_api.DeepL(os.getenv("DEEPL_API_KEY"))
    translations = deepl.translate(source_language="EN", target_language=target_language, texts=[text])
    return translations[0]['text']

def translate_with_progress_bar(strings:list[str], target_language:str) -> list[str]:
    max_width = len(str(len(strings)))  # maximal number width on-screen
    pr = lambda x: (str(x).ljust(max_width) + '/' + str(len(strings)))
    for idx, string in enumerate(strings):
        print('\rtranslating… ' + pr(idx), end='', flush=True)
        yield translated(string, target_language)
    print('\r', end='')


def get_deepl_info():
    return deepl_api.DeepL(os.getenv("DEEPL_API_KEY")).usage_information()

try:
    MAX_CHAR_DEEPL = get_deepl_info().character_limit
except AttributeError:
    print(f'DeepL is not correctly setupped (DEEPL_API_KEY envar). No translation available.')
    MAX_CHAR_DEEPL = None


def show_lists(list_dir:str, width:int=80):
    lists = load_lists(list_dir)
    print(f"{len(lists)} lists are available.")
    for listname, items in lists.items():
        print(listname + ':', len(items), f"items ({get_list_stat(items, ret=str)})")

def json_from_html(html_lines:list[str]) -> list[str]:
    return sorted(list(l.strip('",') for l in map(str.strip, html_lines) if ok(l)))

def save_lists(lists_file:str, lists:dict):
    jsondata = json.dumps(lists)
    with open(lists_file, 'w') as fd:
        fd.write(jsondata)
def load_lists(lists_file:str) -> dict:
    if not os.path.exists(lists_file):
        print(f"List file {lists_file} doesn't exists yet. Creating it.")
        with open(lists_file, 'w') as fd:
            fd.write('{}\n')
    with open(lists_file) as fd:
        return json.load(fd)


def ok(s:str) -> bool:
    return s.startswith('"') and s.endswith('",')
def formt_line_content(idx:int, s:str, w:int) -> str:
    s = s.strip('," \n')
    s = textwrap.fill(s, w)
    s = textwrap.indent(s, '   ')
    idx = '00' if idx == 100 else f'{idx:2d}'
    return idx + ' ' + s[3:]

def without_prefix(url:str, prefix:str=URL_PREFIX) -> str:
    "Return the same url, without the given prefix"
    return url[len(prefix):] if url.startswith(prefix) else url

def url_to_readablename(url:str, ext:str) -> str:
    return without_prefix(url).lower().strip('-/0123456789') + '.' + ext


def get_missing_pages(asked_pages, page_dir:str):
    "Create html backups of given webpages"
    assert os.path.isdir(page_dir)
    for asked_page in map(without_prefix, asked_pages):
        pagefile = os.path.join(page_dir, url_to_readablename(asked_page, 'html'))
        if os.path.exists(pagefile):
            continue  # that page was already parsed
        with open(pagefile, 'w') as fd:
            fd.write(get_url(URL_PREFIX + asked_page))
        print(f'Page {pagefile} saved.')


def parse_lists(page_dir:str, lists_file:str):
    "Put json-encoded lists found in webpages of page dir into the list dir"
    lists = load_lists(lists_file)
    for fname in glob.glob(os.path.join(page_dir, '*.html')):
        name = os.path.splitext(os.path.split(fname)[1])[0]  # get name without ext nor path
        with open(fname) as ifd:
            thelist = json_from_html(ifd)
        if name in lists:  # already present
            if thelist != lists[name]:  # warns that it differs
                print(f"NOTE: List {name} has changed since last parsing. No change made. Here are the first chars of each list version:")
                print('   ', str(thelist)[:50])
                print('   ', str(lists[name])[:50])
            continue
        lists[name] = thelist
        print(f'list {name} encoded ({get_list_stat(thelist, ret=str)}).')
    save_lists(lists_file, lists)


def get_list_stat(strings:list[str], *, ret=float) -> print or str or float:
    nb_char = sum(map(len, strings))
    if MAX_CHAR_DEEPL:
        percent_deepl = round(nb_char / MAX_CHAR_DEEPL * 100, 2)
        percent_deepl = f", {percent_deepl}% of deepl limit"
    else:
        percent_deepl = ''
    if ret is str:
        return f"{nb_char} characters{percent_deepl}"
    elif ret is print:
        print(get_list_stat(strings, ret=str))
    else:
        return nb_char, percent_deepl


def translate_lists(lists_file:str, french_file:str, target_language:str, prompt:bool=False):
    "Translate lists that are not yet present in the french dir"
    lists = load_lists(lists_file)
    french_lists = load_lists(french_file)
    if prompt:  info = get_deepl_info()  # needed for first loop
    to_translate = []
    try:
        for listname, thelist in lists.items():
            if listname in french_lists:
                continue
            if prompt:
                ans = input(f"Translate {listname} ? ({round(sum(map(len, thelist)) / info.character_limit * 100, 2)}%/{round(info.character_count / info.character_limit * 100, 2)}% deepl usage) [y/N]")
                if ans.lower() not in {'y', 'yes', 'oui', 'o'}:
                    continue
                if ans.lower() in {'q', 'quit', 'exit', ':q'}:
                    break
            to_translate.append(listname)
    except KeyboardInterrupt:
        pass
    try:
        for listname in to_translate:
            # listname_fr = translated(listname.replace('-', ' '), target_language).replace(' ', '-')
            listname_fr = listname  # don't translate ! This would make as if it doesn't exists…
            thelist_fr = list(translate_with_progress_bar(lists[listname], target_language))
            french_lists[listname_fr] = thelist_fr
            info = get_deepl_info()
            print(f"\rlist {listname} translated ({round(info.character_count / info.character_limit * 100, 2)}% deepl usage).")
    except KeyboardInterrupt:
        pass
    finally:
        save_lists(french_file, french_lists)


def render_lists(lists_file:str, render_dir:str, width:int=80) -> [str]:
    lists = load_lists(lists_file)
    for listname, items in lists.items():
        fname = os.path.join(render_dir, listname + '.txt')
        yield fname, ''.join((render_list(listname, items, width=width)))

def render_list(title:str, items:list, width:int=80) -> [str]:
    yield title.replace('-', ' ').center(width) + '\n\n'
    for idx, item in enumerate(items, start=1):
        yield formt_line_content(idx, item, width) + '\n'




if __name__ == "__main__":
    args = parse_cli()

    DATA_DIR = 'data'
    PAGE_DIR = DATA_DIR + '/pages'
    LIST_FILE = DATA_DIR + '/lists.json'
    FRENCH_LIST_FILE = DATA_DIR + '/lists-fr.json'
    RENDER_DIR = DATA_DIR + '/render/'
    RENDER_FR_DIR = DATA_DIR + '/render-fr/'
    os.makedirs(PAGE_DIR, exist_ok=True)  # html pages
    os.makedirs(RENDER_DIR, exist_ok=True)  # rendered pages
    os.makedirs(RENDER_FR_DIR, exist_ok=True)  # rendered pages

    get_missing_pages(args.targets, PAGE_DIR)
    parse_lists(PAGE_DIR, LIST_FILE)
    if MAX_CHAR_DEEPL and args.translate:
        translate_lists(LIST_FILE, FRENCH_LIST_FILE, args.translate_to, prompt=True)
    else:
        show_lists(LIST_FILE, width=90)

    print('\n')
    for fname, content in render_lists(LIST_FILE, RENDER_DIR, width=args.width):
        with open(fname, 'w') as fd:
            fd.write(content)
        print(f"{fname} rendered")

    print('\n')
    for fname, content in render_lists(FRENCH_LIST_FILE, RENDER_FR_DIR, width=args.width):
        with open(fname, 'w') as fd:
            fd.write(content)
        print(f"{fname} rendered")

    if MAX_CHAR_DEEPL:
        print('\n')
        info = get_deepl_info()
        print(f"Current Deepl usage information: {round(info.character_count / info.character_limit * 100, 2)}% usage")
