from argparse import ArgumentParser
import vapoursynth as vs
from random import choice, choices
import re
import os

core = vs.core

parser = ArgumentParser('Take screenshots of a file.')
parser.add_argument('clip', metavar='clip', type=str, help='Path to video file')
parser.add_argument('--frames', '-f', dest='frames', type=int, nargs='+',
                    help='List of frames (space-separated), optional')
parser.add_argument('--num-frames', '-n', dest='num_frames', type=int, nargs='?',
                    help='Number of screenshots to take, default=10')

args = parser.parse_args()

filename = args.clip
frames = args.frames
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
    clip = imwri.Write(clip, 'png', os.path.join(save_path, '%d.png'))

    for frame in frames:
        print('Writing {:s}/{:d}.png'.format(save_path, frame))
        clip.get_frame(frame)
