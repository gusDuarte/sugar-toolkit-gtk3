# Copyright (C) 2006-2007, Red Hat, Inc.
# Copyright (C) 2007, One Laptop Per Child
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

"""MIME helpers based on freedesktop specification.

STABLE.
"""

import os
import logging
import gettext

from gi.repository import GdkPixbuf

from sugar3 import _sugarbaseext

_ = lambda msg: gettext.dgettext('sugar-base', msg)

GENERIC_TYPE_TEXT = 'Text'
GENERIC_TYPE_IMAGE = 'Image'
GENERIC_TYPE_AUDIO = 'Audio'
GENERIC_TYPE_VIDEO = 'Video'
GENERIC_TYPE_LINK = 'Link'


def _get_supported_image_mime_types():
    mime_types = []
    for image_format in GdkPixbuf.Pixbuf.get_formats():
        mime_types.extend(image_format.get_mime_types())
    return mime_types


_extensions = {}
_globs_timestamps = []
_generic_types = [
{
    'id': GENERIC_TYPE_TEXT,
    'name': _('Text'),
    'icon': 'text-x-generic',
    'types': [
        'text/plain', 'text/rtf', 'application/pdf', 'application/x-pdf',
        'text/html', 'application/vnd.oasis.opendocument.text',
        'application/rtf', 'text/rtf', 'application/epub+zip'],
},
{
    'id': GENERIC_TYPE_IMAGE,
    'name': _('Image'),
    'icon': 'image-x-generic',
    'types': _get_supported_image_mime_types(),
},
{
    'id': GENERIC_TYPE_AUDIO,
    'name': _('Audio'),
    'icon': 'audio-x-generic',
    'types': [
        'audio/ogg', 'audio/x-wav', 'audio/wav', 'audio/x-vorbis+ogg',
        'audio/x-mpegurl', 'audio/mpegurl', 'audio/mpeg', 'audio/x-scpls'],
},
{
    'id': GENERIC_TYPE_VIDEO,
    'name': _('Video'),
    'icon': 'video-x-generic',
    'types': ['video/ogg', 'application/ogg', 'video/x-theora+ogg',
              'video/x-theora', 'video/x-mng', 'video/mpeg4',
              'video/mpeg-stream', 'video/mpeg', 'video/mpegts', 'video/mpeg2',
              'video/mpeg1', 'video/x-cdxa', 'video/x-ogm+ogg', 'video/x-flv',
              'video/mp4', 'video/x-matroska', 'video/x-msvideo',
              'application/x-ogm-video', 'video/quicktime', 'video/x-quicktime'
              'video/avi'],
},
{
    'id': GENERIC_TYPE_LINK,
    'name': _('Link'),
    'icon': 'text-uri-list',
    'types': ['text/x-moz-url', 'text/uri-list'],
}]


class ObjectType(object):

    def __init__(self, type_id, name, icon, mime_types):
        self.type_id = type_id
        self.name = name
        self.icon = icon
        self.mime_types = mime_types


def get_generic_type(type_id):
    types = get_all_generic_types()
    for generic_type in types:
        if type_id == generic_type.type_id:
            return generic_type


def get_all_generic_types():
    types = []
    for generic_type in _generic_types:
        object_type = ObjectType(generic_type['id'], generic_type['name'],
                                 generic_type['icon'], generic_type['types'])
        types.append(object_type)
    return types


def get_for_file(file_name):
    if file_name.startswith('file://'):
        file_name = file_name[7:]

    file_name = os.path.realpath(file_name)

    mime_type = _sugarbaseext.get_mime_type_for_file(file_name)
    if mime_type == 'application/octet-stream':
        if _file_looks_like_text(file_name):
            return 'text/plain'
        else:
            return 'application/octet-stream'

    return mime_type


def get_from_file_name(file_name):
    return _sugarbaseext.get_mime_type_from_file_name(file_name)


def get_mime_icon(mime_type):
    generic_type = _get_generic_type_for_mime(mime_type)
    if generic_type:
        return generic_type['icon']

    return mime_type.replace('/', '-')


def get_mime_description(mime_type):
    generic_type = _get_generic_type_for_mime(mime_type)
    if generic_type:
        return generic_type['name']

    import gio
    return gio.content_type_get_description(mime_type)


def get_mime_parents(mime_type):
    return _sugarbaseext.list_mime_parents(mime_type)


def get_primary_extension(mime_type):
    global _extensions
    global _globs_timestamps

    dirs = []

    if 'XDG_DATA_HOME' in os.environ:
        dirs.append(os.environ['XDG_DATA_HOME'])
    else:
        dirs.append(os.path.expanduser('~/.local/share/'))

    if 'XDG_DATA_DIRS' in os.environ:
        dirs.extend(os.environ['XDG_DATA_DIRS'].split(':'))
    else:
        dirs.extend(['/usr/local/share/', '/usr/share/'])

    timestamps = []
    globs_path_list = []
    for f in dirs:
        globs_path = os.path.join(f, 'mime', 'globs')
        if os.path.exists(globs_path):
            mtime = os.stat(globs_path).st_mtime
            timestamps.append([globs_path, mtime])
            globs_path_list.append(globs_path)

    if timestamps != _globs_timestamps:
        # Clear the old extensions list
        _extensions = {}

        # FIXME Properly support these types in the system. (#4855)
        _extensions['audio/ogg'] = 'ogg'
        _extensions['video/ogg'] = 'ogg'

        for globs_path in globs_path_list:
            globs_file = open(globs_path)
            for line in globs_file.readlines():
                line = line.strip()
                if not line.startswith('#'):
                    line_type, glob = line.split(':')
                    if glob.startswith('*.'):
                        _extensions[line_type] = glob[2:]

        _globs_timestamps = timestamps

    if mime_type in _extensions:
        return _extensions[mime_type]
    else:
        return None


_MIME_TYPE_BLACK_LIST = [
    # Target used only between gtk.TextBuffer instances
    'application/x-gtk-text-buffer-rich-text',
]


def choose_most_significant(mime_types):
    logging.debug('Choosing between %r.', mime_types)
    if not mime_types:
        return ''

    if 'text/uri-list' in mime_types:
        return 'text/uri-list'

    for mime_category in ['image/', 'application/']:
        for mime_type in mime_types:

            if mime_type.startswith(mime_category) and \
               mime_type not in _MIME_TYPE_BLACK_LIST:
                # skip mozilla private types (second component starts with '_'
                # or ends with '-priv')
                if mime_type.split('/')[1].startswith('_') or \
                   mime_type.split('/')[1].endswith('-priv'):
                    continue

                # take out the specifier after ';' that mozilla likes to add
                mime_type = mime_type.split(';')[0]
                logging.debug('Choosed %r!', mime_type)
                return mime_type

    if 'text/x-moz-url' in mime_types:
        logging.debug('Choosed text/x-moz-url!')
        return 'text/x-moz-url'

    if 'text/html' in mime_types:
        logging.debug('Choosed text/html!')
        return 'text/html'

    if 'text/plain' in mime_types:
        logging.debug('Choosed text/plain!')
        return 'text/plain'

    logging.debug('Returning first: %r.', mime_types[0])
    return mime_types[0]


def split_uri_list(uri_list):
    return _sugarbaseext.uri_list_extract_uris(uri_list)


def _file_looks_like_text(file_name):
    f = open(file_name, 'r')
    try:
        sample = f.read(256)
    finally:
        f.close()

    if '\000' in sample:
        return False

    for encoding in ('ascii', 'latin_1', 'utf_8', 'utf_16'):
        try:
            unicode(sample, encoding)
            return True
        except Exception:
            pass

    return False


def _get_generic_type_for_mime(mime_type):
    for generic_type in _generic_types:
        if mime_type in generic_type['types']:
            return generic_type
    return None
