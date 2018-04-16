import glob
import os
import re
import shutil
import subprocess
import sys
import vapoursynth as vs
from argparse import ArgumentParser
from random import choice, choices

core = vs.core

parser = ArgumentParser(
    'Take screenshots and extract subtitles/fonts of a file. Can burn in subtitles for screenshots.')
parser.add_argument('clip', metavar='clip', type=str, help='Path to video file')
parser.add_argument('--frames', '-f', dest='frames', type=int, nargs='+',
                    help='List of frames (space-separated), optional')
parser.add_argument('--num-frames', '-n', dest='num_frames', type=int, nargs='?',
                    help='Number of screenshots to take, default=6')
parser.add_argument('--subtitle-track', '-s', dest='sub_track', type=int, const=1, nargs='?',
                    help="Subtitle track for screenshots. Default is no subtitles")
parser.add_argument('--zip', '-z', dest='zip_s', nargs='?', const="True",
                    help="Zip archive the screenshot folder to main directory. Still call --remove-sources if needed")
parser.add_argument('--remove-sources', '-rms', dest='remove_sources', nargs='?', const="True",
                    help="Remove all sources (subs/fonts) in the dir after screenshotting")
parser.add_argument('--remove-dir', '-rmd', dest='remove_dir', nargs='?', const="True",
                    help="Remove screenshot directory and all files. Will be called after --zip if included")
parser.add_argument('--extract-only', '-exto', dest='extract_only', nargs='?', const="True",
                    help="""Don't do any screenshots and only extract fonts. Can also extract one subtitle track
                     with fonts using --sutbtitle-track""")
parser.add_argument('--remove-index', '-rmi', dest='remove_index', nargs='?', const="True",
                    help="Remove index file generated by vapoursynth loading the file")
parser.add_argument('--save-path', '-path', dest='save_path', nargs='?', const="True",
                    help="""Save path of all generated files. Still creates a new folder in location. Default is the 
                    location of the video file""")
parser.add_argument('--quiet', '-q', dest='quiet', nargs='?', const="True", help="Don't print anything")

args = parser.parse_args()
filename = args.clip
frames = args.frames
sub_track = args.sub_track
remove_sources = args.remove_sources
to_zip = args.zip_s
remove_dir = args.remove_dir
extract_only = args.extract_only
remove_index = args.remove_index
user_save_path = args.save_path
num_frames = args.num_frames if args.num_frames is not None else 6
if args.quiet is not None:
    sys.stdout = open(os.devnull, 'w')


def open_clip(path: str) -> vs.VideoNode:
    """Load clip into vapoursynth"""
    if path.endswith('ts'):  # .m2ts and .ts
        clip = core.lsmas.LWLibavSource(path)
    else:
        clip = core.ffms2.Source(path)
    clip = clip.resize.Spline36(format=vs.RGB24, matrix_in_s='709' if clip.height > 576 else '601')
    return clip


def get_frame_numbers(clip, n):
    """Get frame numbers to get screenshots of based off of length of clip/num screenshots"""
    length = len(open_clip(clip))
    frames = choices(range(length // 10, length // 10 * 9), k=n)
    frames = set([x // 100 for x in frames])
    while len(frames) < num_frames:
        frames.add(choice(range(length // 10, length // 10 * 9)) // 100)
    return [x * 100 for x in frames]


def get_sub_track_id(file, num):
    """Returns wanted sub track id and type of subs"""
    # could also use ffprobe to json as it turns out
    try:
        raw_info = subprocess.check_output(["mkvmerge", "-i", file],
                                           stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as ex:
        print(ex)
        sys.exit(1)
    pattern = re.compile('(\d+): subtitles \((.*?)\)')

    mat = pattern.findall(str(raw_info))
    # num is 1 indexed, get only the num track in file
    mat = mat[num - 1]

    if mat:
        # track num, type of subs
        return mat[0], mat[1]
    else:
        return None, None


def get_subs(file, save_path, track):
    """Extracts subs"""
    track_id_m, sub_type = get_sub_track_id(file, track)
    if track_id_m is None:
        print("Error: Did not find subtitles for track {}. Exiting".format(track))
        sys.exit(1)

    sub_ext = parse_sub_type(sub_type)
    # don't include extension for vobsubs since it creates a .sub and .idx
    if sub_ext == ".idx":
        path = os.path.join(save_path, os.path.splitext(os.path.basename(file))[0])
    else:
        path = os.path.join(save_path, os.path.splitext(os.path.basename(file))[0] + sub_ext)

    try:
        with open(os.devnull, "w") as f:
            proc = subprocess.call(["mkvextract", "tracks", file,
                                    track_id_m + ":" + path], stdout=f)
            if proc != 0:
                print("ERROR: Could not extract subtitles despite finding some")
                sys.exit(1)

        print("Extracted subtitle to {}".format(path))
    except subprocess.CalledProcessError:
        print("ERROR: CalledProcessError: Could not extract subtitles despite finding some")
        sys.exit(1)

    return track_id_m, parse_sub_type(sub_type)


def get_fonts(file, save_path):
    """Extracts fonts"""
    try:
        raw_info = subprocess.check_output(["mkvmerge", "-i", file],
                                           stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as ex:
        print(ex)
        sys.exit(1)

    pattern = re.compile('Attachment ID (\d+).*?type \'(.*?)\'.*? name \'(.*?)\'')
    all_attachments = pattern.findall(str(raw_info))

    if all_attachments is None:
        print("Found no attachments")
        return None

    to_extract = []
    # check for actual font attachments
    for attach in all_attachments:
        ext = os.path.splitext(attach[2])[1].lower()
        types = ("application/x-truetype-font", "application/vnd.ms-opentype")
        if attach[1] in types and (ext == ".otf" or ext == ".ttf"):
            # working as intended
            to_extract.append([attach[0], attach[2]])
        elif attach[1] in types and not (ext == ".otf" or ext == ".ttf"):
            # notify user about mismatch but still extract
            print("Found font type without otf/ttf extension - still extracting")
            to_extract.append([attach[0], attach[2]])
        elif attach[1] not in types and (ext == ".otf" or ext == ".ttf"):
            # notify user about mismatch but still extract
            print("Found font with extension but not of correct type - still extracting")
            to_extract.append([attach[0], attach[2]])

    if not to_extract:
        print("Found no font attachments")
        return None

    # I tried to combine this into one long string, list comprehension etc. but couldn't get it to work
    # going to call the command multiple times for each font for now :\
    # think its an issue of the os.path.join to string? even added quotes to the filename but nah

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


def render_subs(clip, filename, subs_extension, folder_path):
    no_ext = os.path.splitext(os.path.basename(filename))[0]
    sub_file = os.path.join(folder_path, no_ext + subs_extension)

    if subs_extension == ".pgs" or subs_extension == ".idx":
        burned = core.sub.ImageFile(clip, file=sub_file, blend=True)
    else:
        burned = core.sub.TextFile(clip, file=sub_file, fontdir=folder_path, blend=True,
                                   primaries_s='709' if clip.height > 576 else '601')

    return imwri.Write(burned, 'png', os.path.join(save_path, '%d.png'))


def parse_sub_type(sub_type):
    """Gets file extension for subtitle type from mkvmerge -i"""
    if sub_type == "HDMV PGS":
        return ".pgs"
    elif sub_type == "SubStationAlpha":
        return ".ass"
    elif sub_type == "SubRip/SRT":
        return ".srt"
    elif sub_type == "VobSub":
        # creates both a .sub and a .idx but only need idx
        return ".idx"
    else:
        print("Error: Didn't get a known sub type - exiting")
        sys.exit(1)


if __name__ == '__main__':
    if extract_only:
        # extract only subs/fonts and exit
        dir_name = re.split(r'[\\/]', filename)[-1].rsplit('.', 1)[0]
        if not os.path.exists(dir_name):
            os.mkdir(os.path.join(os.getcwd(), dir_name))
        save_path = os.path.join(os.getcwd(), dir_name)
        if sub_track:
            get_subs(filename, save_path, sub_track)
        else:
            print("Sub track not specified so not grabbing")
        get_fonts(filename, save_path)
        sys.exit(0)

    if frames is None:
        print("Indexing... May take a while in the file size is large")
        frames = get_frame_numbers(filename, num_frames)
    print('Requesting frames:', *frames)

    if hasattr(core, 'imwri'):
        imwri = core.imwri
    elif hasattr(core, 'imwrif'):
        imwri = core.imwrif
    else:
        raise AttributeError('Either imwri or imwrif must be installed.')
    dir_name = re.split(r'[\\/]', filename)[-1].rsplit('.', 1)[0]
    clip = open_clip(filename)

    if user_save_path:
        if not os.path.exists(os.path.join(user_save_path, dir_name)):
            # create folder in specified save path location
            os.mkdir(os.path.join(user_save_path, dir_name))
        save_path = os.path.join(os.path.dirname(user_save_path), dir_name)
    else:
        if not os.path.exists(os.path.join(os.path.dirname(filename), dir_name)):
            # create folder in same directory as video file
            os.mkdir(os.path.join(os.path.dirname(filename), dir_name))
        save_path = os.path.join(os.path.dirname(filename), dir_name)

    print(save_path)

    if sub_track:
        # Extract subs and fonts and render them if sub track is requested
        # I don't gotta pass these global vars but I will darn it
        track_id, subs_extension = get_subs(filename, save_path, sub_track)
        get_fonts(filename, save_path)
        clip = render_subs(clip, filename, subs_extension, save_path)
    else:
        clip = imwri.Write(clip, 'png', os.path.join(save_path, '%d.png'))

    for frame in frames:
        print('Writing {:s}/{:d}.png'.format(save_path, frame))
        clip.get_frame(frame)
    print("Done writing screenshots")

    if remove_sources:
        remove_types = ('*.pgs', '*.ass', '*.ttf', '*.otf', '*.sub', '*.idx', '*.srt')
        matching_files = []
        os.chdir(save_path)  # eh couldnt get glob to work in different directory for some reason
        for files in remove_types:
            matching_files.extend(glob.glob(files))
        for files in matching_files:
            os.remove(files)
        print("Removed sources")

    if to_zip:
        shutil.make_archive(save_path, 'zip', save_path)
        print("Zipped screenshot directory")

    if remove_dir:
        try:
            shutil.rmtree(save_path)
        except OSError as e:
            print("Error: %s - %s." % (e.filename, e.strerror))
        else:
            print("Removed screenshot directory")

    if remove_index:
        # could be done better
        try:
            os.remove(os.path.basename(filename) + ".lwi")
            print("Removed .lwi")
            sys.exit(0)
        except OSError:
            pass
        try:
            os.remove(os.path.basename(filename) + ".ffindex")
            print("Removed .ffindex")
        except OSError:
            print("Unable to remove index")
