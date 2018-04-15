from argparse import ArgumentParser
import vapoursynth as vs
from random import choice, choices
import subprocess
import re
import os
import sys
from collections import namedtuple

core = vs.core

parser = ArgumentParser('Take screenshots of a file.')
parser.add_argument('clip', metavar='clip', type=str, help='Path to video file')
parser.add_argument('--frames', '-f', dest='frames', type=int, nargs='+',
                    help='List of frames (space-separated), optional')
parser.add_argument('--num-frames', '-n', dest='num_frames', type=int, nargs='?',
                    help='Number of screenshots to take, default=10')
parser.add_argument('--subtitle-track', '-s', dest='sub_track', type=int, const=1, nargs='?',
                     help="Subtitle track for screenshots")

args = parser.parse_args()

filename = args.clip
frames = args.frames
sub_track = args.sub_track
num_frames = args.num_frames if args.num_frames is not None else 10


def open_clip(path: str) -> vs.VideoNode:
    if path.endswith('ts'):  # .m2ts and .ts
        clip = core.lsmas.LWLibavSource(path)
    else:
        clip = core.ffms2.Source(path)
    clip = clip.resize.Spline36(format=vs.RGB24, matrix_in_s='709' if clip.height > 576 else '601')
    return clip


def get_frame_numbers(clip, n):
    length = len(open_clip(clip))
    frames = choices(range(length // 10, length // 10 * 9), k=n)
    frames = set([x // 100 for x in frames])
    while len(frames) < num_frames:
        frames.add(choice(range(length // 10, length // 10 * 9)) // 100)
    return [x * 100 for x in frames]

def get_track_id(file, num):
    try:
        raw_info = subprocess.check_output(["mkvmerge", "-i", file],
                                            stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as ex:
        print(ex)
        sys.exit(1)
    pattern = re.compile('(\d+): subtitles \((.*?)\)')

    mat = pattern.findall(str(raw_info))
    # num is 1 indexed, get only the num track in file
    mat = mat[num-1]

    if mat:
        # track num, type of subs
        return mat[0], mat[1]
    else:
        return None, None

def get_subs(file, save_path, track):
    track_id, sub_type = get_track_id(file, track)
    if track_id == None:
        print("Error: Did not find subtitles")
        sys.exit(1)

    sub_ext = parse_sub_type(sub_type)
    # don't include extension because mkvextract does that for vobsubs only?
    if sub_ext == "VOBSUBS":
        path = os.path.join(save_path, os.path.splitext(os.path.basename(file))[0])
    else:
        path = os.path.join(save_path, os.path.splitext(os.path.basename(file))[0] + sub_ext)

    try:
        with open(os.devnull, "w") as f:
            proc = subprocess.call(["mkvextract", "tracks", file,
                        track_id + ":" + path], stdout=f)

            if proc != 0:
                print("ERROR: Could not extract subtitles despite finding some")
                sys.exit(1)

        print("Extracted subtitle to {}".format(path))
    except subprocess.CalledProcessError:
        print("ERROR: CalledProcessError: Could not extract subtitles despite finding some")
        sys.exit(1)

    return track_id, parse_sub_type(sub_type)


def get_fonts(file, save_path):
    try:
        raw_info = subprocess.check_output(["mkvmerge", "-i", file],
                                            stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as ex:
        print(ex)
        sys.exit(1)

    pattern = re.compile('Attachment ID (\d+).*?type \'(.*?)\'.*? name \'(.*?)\'')

    all_attachments = pattern.findall(str(raw_info))

    if all_attachments == None:
        print("Found no attachments")
        return None

    to_extract = []

    # check for actual font attachments
    for attach in all_attachments:
        ext = os.path.splitext(attach[2])[1].lower()
        if attach[1] == "application/x-truetype-font" and (ext == ".otf" or ext == ".ttf"):
            # working as intended
            to_extract.append([attach[0], attach[2]])
        elif attach[1] == "application/x-truetype-font" and not (ext == ".otf" or ext == ".ttf"):
            # notify user about mismatch but still extract
            print("Found font type without otf/ttf extension - still extracting")
            to_extract.append([attach[0], attach[2]])
        elif attach[1] != "application/x-truetype-font" and (ext == ".otf" or ext == ".ttf"):
            print("Found font with extension but not of correct type - still extracting")
            to_extract.append([attach[0], attach[2]])

    if to_extract == []:
        print("Found no font attachments")
        return None

    # I tried to combine this into one long string, list comprehension etc. but couldn't get it to work
    # going to call the command multiple times for each font for now :\
    # think its an issue of the os.path.join to string?

    try:
        for a in to_extract:
            font = a[0] + ":" + os.path.join(save_path, a[1])
            with open(os.devnull, "w") as f:
                proc = subprocess.call(["mkvextract", "attachments", file, font], stdout=f)
            if proc != 0:
                print("ERROR: Could not extract font {} despite finding it".format(font))
                sys.exit(1)

        print("Extracted fonts to {}".format(save_path))
    except subprocess.CalledProcessError:
        print("ERROR: CalledProcessError: Could not extract fonts despite finding some")
        sys.exit(1)

    sys.exit(0)

def parse_sub_type(type):
    if type == "HDMV PGS":
        return ".pgs"
    elif type == "SubStationAlpha":
        return ".ass"
    elif type == "SubRip/SRT":
        return ".srt"
    elif type == "VobSub":
        # creates both a .sub and a .idx - so check after creation
        return "VOBSUBS"
    else:
        print("Error: Didn't get a known sub type - exiting")
        sys.exit(1)

if __name__ == '__main__':

    if frames is None:
        frames = get_frame_numbers(filename, num_frames)
    print('Requesting frames:', *frames)

    if hasattr(core, 'imwri'):
        imwri = core.imwri
    elif hasattr(core, 'imwrif'):
        imwri = core.imwrif
    else:
        raise AttributeError('Either imwri or imwrif must be installed.')

    dir_name = re.split(r'[\\/]', filename)[-1].rsplit('.', 1)[0]
    if not os.path.exists(dir_name):
        os.mkdir(os.path.join(os.getcwd(), dir_name))
    clip = open_clip(filename)
    save_path = os.path.join(os.getcwd(), dir_name)
    if sub_track:
        track_id, subs_extension = get_subs(filename, save_path, sub_track)
        get_fonts(filename, save_path)
        sys.exit(0)
    clip = imwri.Write(clip, 'png', os.path.join(save_path, '%d.png'))

    for frame in frames:
        print('Writing {:s}/{:d}.png'.format(save_path, frame))
        clip.get_frame(frame)
