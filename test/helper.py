import sys
import os
import tempfile
import logging
import shutil
from contextlib import contextmanager
from StringIO import StringIO

import beets
from beets import autotag
from beets import plugins
from beets.autotag import AlbumInfo, TrackInfo, \
                          AlbumMatch, TrackMatch, \
                          recommendation
from beets.autotag.hooks import Distance
from beets.library import Item
from beets.mediafile import MediaFile

from beetsplug import check

logging.getLogger('beets').propagate = True

class LogCapture(logging.Handler):

    def __init__(self):
        super(LogCapture, self).__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.msg)


@contextmanager
def captureLog(logger='beets'):
    capture = LogCapture()
    log = logging.getLogger(logger)
    log.addHandler(capture)
    try:
        yield capture.messages
    finally:
        log.removeHandler(capture)

@contextmanager
def captureStdout():
    org = sys.stdout
    sys.stdout = StringIO()
    try:
        yield sys.stdout
    finally:
        sys.stdout = org

@contextmanager
def controlStdin(input=None):
    org = sys.stdin
    sys.stdin = StringIO(input)
    sys.stdin.encoding = 'utf8'
    try:
        yield sys.stdin
    finally:
        sys.stdin = org

class TestHelper(object):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        plugins._classes = [check.CheckPlugin]

    def tearDown(self):
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir)

    def setupBeets(self):
        self.temp_dir = tempfile.mkdtemp()
        os.environ['BEETSDIR'] = self.temp_dir

        self.config = beets.config
        self.config.clear()
        self.config.read()

        self.config['plugins'] = []
        self.config['verbose'] = True
        self.config['color'] = False
        self.config['threaded'] = False
        self.config['import']['copy'] = False

        self.libdir = os.path.join(self.temp_dir, 'libdir')
        os.mkdir(self.libdir)
        self.config['directory'] = self.libdir

        self.lib = beets.library.Library(self.config['library'].as_filename(),
                      self.libdir)

        self.fixture_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        
    def setupImportDir(self, files):
        self.import_dir = os.path.join(self.temp_dir, 'import')
        if not os.path.isdir(self.import_dir):
            os.mkdir(self.import_dir)
        for file in files:
            src = os.path.join(self.fixture_dir, file)
            shutil.copy(src, self.import_dir)

    def setupFixtureLibrary(self):
        self.import_dir = os.path.join(self.temp_dir, 'import')
        for file in os.listdir(self.fixture_dir):
            src = os.path.join(self.fixture_dir, file)
            dst = os.path.join(self.libdir, file)
            shutil.copy(src, dst)
            item = Item.from_path(dst)
            item.add(self.lib)
            check.set_checksum(item)

    def modifyFile(self, path, title='a different title'):
        mediafile = MediaFile(path)
        mediafile.title = title
        mediafile.save()

    @contextmanager
    def mockAutotag(self):
        mock = AutotagMock()
        mock.install()
        try:
            yield
        finally:
            mock.restore()


class AutotagMock(object):

    def __init__(self):
        self.id = 0

    def nextid(self):
        self.id += 1
        return self.id

    def install(self):
        self._orig_tag_album = autotag.tag_album
        self._orig_tag_item = autotag.tag_item
        autotag.tag_album = self.tag_album
        autotag.tag_item = self.tag_item

    def restore(self):
        autotag.tag_album = self._orig_tag_album
        autotag.tag_item = self._orig_tag_item

    def tag_album(self, items, **kwargs):
        artist = (items[0].artist or '') + ' tag'
        album  = (items[0].album or '') + ' tag'
        mapping = {}
        dist = Distance()
        dist.tracks = {}
        for item in items:
            title = (item.title or '') + ' tag'
            track_info = TrackInfo(title=title, track_id=self.nextid())
            mapping[item] = track_info
            dist.tracks[track_info] = Distance()

        album_info = AlbumInfo(album='album', album_id=self.nextid(),
                               artist='artist', artist_id=self.nextid(),
                               tracks=mapping.values())
        match = AlbumMatch(distance=dist, info=album_info, mapping=mapping,
                           extra_items=[], extra_tracks=[])
        return artist, album, [match], recommendation.strong

    def tag_item(self, item, **kwargs):
        title = (item.title or '') + ' tag'
        track_info = TrackInfo(title=title, track_id=self.nextid())
        match = TrackMatch(distance=Distance(), info=track_info)
        return [match], recommendation.strong