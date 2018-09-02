#!/usr/bin/python3

import os
import sys
import subprocess
import json
import re
import asyncio
from random import randint

from classes.song import Song
from classes.snippet import Snippet
from classes.snippetcollection import SnippetCollection

# TODO: Write documentation and comments
# TODO: Include META tags
# TODO: Update the README

CURR_DIR = os.path.dirname(os.path.realpath(__file__)) + "/"
SCRIPT_DIR = CURR_DIR + "scripts/"

#
# _contents.json interaction
#


def load_downloaded_urls(destination):
    urls = []
    if not os.path.exists(destination):
        os.mkdir(destination)
    else:
        # If it does exist, read the contents.json file to find out what
        # is already downloaded
        if os.path.isfile(destination + "_contents.json"):
            try:
                with open(destination + "_contents.json") as c:
                    urls = json.loads("".join(c.readlines()))
            except json.JSONDecodeError as e:
                print("JSON could not be read correctly.")
                print("Playlist with the destination " + destination)
                print(str(e))
    return urls


def save_downloaded_urls(destination, urls):
    with open(destination + "_contents.json", "w") as c:
        c.write(json.dumps(urls))

#
# Scripts
#


def get_download_script(output_file, url):
    return (
        "youtube-dl " +
        "--quiet " +
        "--extract-audio " +
        "--audio-format mp3 " +
        "--audio-quality 0 " +
        "--output " +
        '"{}_tmp.mp3" '.format(output_file) +
        '{} '.format(url)
    )


def get_normalisation_script(output_file):
    return (
        "ffmpeg " +
        '-i "{}_tmp.mp3" '.format(output_file) +
        "-af loudnorm=I=-16:TP=-1.5:LRA=11 " +
        "-ar 48k " +
        '"{}.mp3" '.format(output_file) +
        "-y " +

        "&& " +
        'rm "{}_tmp.mp3"'.format(output_file)
    )


def get_split_script(input_file, start_time, end_time, output_file):
    return (
        "ffmpeg -i " +
        '"{}" '.format(input_file) +
        "-acodec copy " +
        "-ss {} ".format(start_time) +
        "-to " + end_time + " " +
        "-c:a libmp3lame " +
        '"{}"'.format(output_file)
    )


async def run_script(command):
    process = await asyncio.create_subprocess_shell(
        command,
        shell=True,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL
    )
    stdout, stderr = await process.communicate()
    return (stdout, stderr)

#
# Download
#


async def download_song(song, destination):
    """Downloads the song to the given destination and normalizes it."""
    print('\tDownloading "' + song.TITLE + '"..')

    await run_script(
        get_download_script(
            destination + song.TITLE.replace("/", "").replace('"', "'"),
            song.URL
        ),
    )

    print('\tDownloaded "' + song.TITLE + '"..')
    print('\tNormalizing "' + song.TITLE + '"..')

    await run_script(
        get_normalisation_script(
            destination + song.TITLE.replace("/", "").replace('"', "'"),
        ),
    )

    print('\tNormalized "' + song.TITLE + '"..')


async def download_snippet_collection(snippet_collection, destination):
    print('\tDownloading a temporary file for the snippet collection..')
    temp_title = ""
    for i in range(0, 16):
        temp_title += chr(randint(ord('a'), ord('z')))

    await run_script(
        get_download_script(
            destination + temp_title,
            snippet_collection.URL
        )
    )

    temp_title += "_tmp.mp3"

    tasks = []
    for index in range(0, len(snippet_collection.snippets) - 1):
        snippet_title = (snippet_collection.snippets[index].TITLE).replace(
            "/", "").replace('"', "'")

        print("\t\tSplitting {}..".format(
            snippet_collection.snippets[index].TITLE))

        tasks.append(run_script(
            get_split_script(
                destination + temp_title,
                snippet_collection.snippets[index].START_TIME,
                snippet_collection.snippets[index + 1].START_TIME,
                destination + snippet_title + "_tmp.mp3"
            ) + " && " +
            get_normalisation_script(
                destination +
                snippet_collection.snippets[index].TITLE.replace(
                    "/", "").replace('"', "'")
            )
        ))
    await asyncio.gather(*tasks)

    print("\tDeleting temporary file.")
    await run_script(
        "rm " + destination + temp_title
    )


async def download_playlist(playlist, destination):
    downloaded_urls = load_downloaded_urls(destination)

    # Download every item that is not already downloaded
    tasks = []
    for item in playlist:
        if item.URL not in downloaded_urls:
            if isinstance(item, Song):
                tasks.append(download_song(item, destination))
            elif isinstance(item, SnippetCollection):
                tasks.append(download_snippet_collection(item, destination))
            downloaded_urls.append(item.URL)

    await asyncio.gather(*tasks)
    save_downloaded_urls(destination, downloaded_urls)


async def download_playlists(playlists, destination):
    for playlist in playlists:
        print("* Downloading Playlist '" + playlist + "'.. ")
        await download_playlist(playlists[playlist],
                                destination + "/" + playlist + "/")

#
# Parsing
#


def parse_music(music_content):
    playlists = {}
    playlist = ""
    songs = []
    lines = [x + "\n" for x in music_content.split("\n")]

    index = 0
    while index < len(lines):
        # Save playlist and reset songs
        if lines[index].startswith("** "):
            if playlist != "":
                playlists[playlist] = songs
            playlist = lines[index][3:-1]
            songs = []
        # Add a new song
        elif lines[index].startswith("- "):
            line = lines[index].replace(
                "[", "").replace("- ", "", 1).split("]")
            songs.append(Song(line[1], line[0]))
        # Add a new snippet collection
        elif lines[index].startswith("+ "):
            #
            # Find functions to load data
            #
            start_index = index
            acc = ""
            while lines[index].endswith("\\\n"):
                acc += lines[index][:-1]
                index += 1

            link = re.search("\[\[.+?\]", acc).group(0)
            link = link.replace("[", "").replace("]", "")

            code = acc[acc.find("{"):acc.rfind("};") + 1].replace("\\", "")
            code = json.loads(code)

            title_func = eval(code["title"])
            time_func = eval(code["time"])

            #
            # Load snippet collection
            #
            index = start_index
            while "};" not in lines[index]:
                index += 1
            index += 1

            snippet_collection = SnippetCollection(link)
            while lines[index].endswith("\\\n"):
                title = title_func(lines[index])
                time = time_func(lines[index])
                snippet_collection.snippets.append(Snippet(title, time))
                index += 1
            songs.append(snippet_collection)
        index += 1
    playlists[playlist] = songs
    return playlists


async def main():
    if len(sys.argv) == 2:
        f = sys.argv[1]
    else:
        print("Which music file do you want to parse and download?: ")
        f = input()

    with open(f) as content:
        playlists = parse_music("".join(content.readlines()))

    # Print playlist information
    print("Found {} playlist(s) with {} song(s).".format(
        len(playlists),
        # Count all the songs
        len([s for p in playlists for s in playlists[p] if isinstance(s, Song)]) +
        # Sum all snippets
        sum([len(s.snippets) for p in playlists for s in playlists[p]
             if isinstance(s, SnippetCollection)])
    ))

    if not os.path.exists(CURR_DIR + "music"):
        os.mkdir(CURR_DIR + "music")

    await download_playlists(playlists, CURR_DIR + "music")

    print("Done.")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()
