# vs-screen

Takes screenshots of files using vapoursynth and extracts subs/fonts. Can burn in subtitles to the screenshots if desired or just extract sub(s)/all fonts.

Lazy to do:

- Option for putting frame number text on screenshots
- If mkvextract/mkvmerge -i don't work with mp4 those won't work (untested)

Requirements: Python 3 and vapoursynth built with ImageMagick support (--enable-imwri) and the ffms2 (mkv)/LWLibavSource (m2ts) plugins. Also requires the mkvtoolnix suite of mkvmerge/mkvextract.
