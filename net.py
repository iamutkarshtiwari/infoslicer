# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os
import io
import shutil
import urllib
import urllib2
import uuid
import logging
import html2text
import ConfigParser
from gettext import gettext as _

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

from BeautifulSoup import BeautifulSoup

from sugar3.activity.activity import get_bundle_path, get_activity_root

import book
from edit import OFFLINE_MODE_ACTIVE, TABS
from infoslicer.processing.NewtifulSoup import NewtifulStoneSoup \
        as BeautifulStoneSoup
from infoslicer.processing.MediaWiki_Parser import MediaWiki_Parser
from infoslicer.processing.MediaWiki_Helper import MediaWiki_Helper
from infoslicer.processing.MediaWiki_Helper import PageNotFoundError

logger = logging.getLogger('infoslicer')
elogger = logging.getLogger('infoslicer::except')

proxies = None
WIKI = { 'en.wikipedia.org', 
         'simple.wikipedia.org', 
         'fr.wikipedia.org',
         'de.wikipedia.org',
         'pl.wikipedia.org',
         'es.wikipedia.org'  }

def download_wiki_article(title, wiki, progress, activity):
    if wiki not in WIKI:

        try:
            #progress.set_label(_('"%s" download in progress...') % title)
            OFFLINE_MODE_ACTIVE = True
            title = (title.strip()).replace(' ', '+')
            search = _read_configuration()[0] + _read_configuration()[1] + "%s" % (title)
            f = urllib2.urlopen(search)
            document = f.read()
            f.close()
            
            # Extracts textual content from the offline wiki page
            h = html2text.HTML2Text()
            h.ignore_links = True
            h.ignore_images = True
            text = str(h.handle(document))

            # Image downloads path
            dir_path = os.path.join(get_activity_root(), 'data', 'book')
            uid = str(uuid.uuid1())            
            text_path = os.path.join(dir_path, uid,'content.txt')
            if not os.path.exists(os.path.join(dir_path, uid)):
                os.makedirs(os.path.join(dir_path, uid), 0777)

            file = open(text_path, "w+")
            file.write(text)
            file.close()
            image_list = zim_image_handler(dir_path, uid, document)
            TABS[1].gallery.set_image_list(image_list)

            return text_path
        
        except urllib2.URLError, e:
            elogger.debug('download_and_add: %s' % e)
            progress.set_label(_('"%s" could not be found. Check your connection') % title.replace('+', ' '))
            return 'Error'    

    else:    
        try:
            OFFLINE_MODE_ACTIVE = False
            progress.set_label(_('"%s" download in progress...') % title)
            article, url = MediaWiki_Helper().getArticleAsHTMLByTitle(title, wiki)

            progress.set_label(_('Processing "%s"...') % title)
            parser = MediaWiki_Parser(article, title, url)
            contents = parser.parse()

            progress.set_label(_('Downloading "%s" images...') % title)
            book.wiki.create(title + _(' (from %s)') % wiki, contents)

            progress.set_label(_('"%s" successfully downloaded') % title)

        except PageNotFoundError, e:
            elogger.debug('download_and_add: %s' % e)
            progress.set_label(_('"%s" could not be found') % title)

        except Exception, e:
            elogger.debug('download_and_add: %s' % e)
            progress.set_label(_('Error downloading "%s"; check your connection') % title)

        return ''    

def _read_configuration(file_name='get-url.cfg'):
    '''
    Reads the source 'uri' and 'query_uri' of the SchoolServer Wikipedia
    from get-url.cfg file
    '''
    config = ConfigParser.ConfigParser()
    config.readfp(open(file_name))
    if config.has_option('SchoolServer', 'source_uri'):
        source_uri = str(config.get('SchoolServer', 'source_uri'))
    else:
        logging.error('No school server URI found')
        return             

    if config.has_option('SchoolServer', 'query_uri'):
        query_uri = str(config.get('SchoolServer', 'query_uri'))
    else:
        logging.error('School server QUERY_URI not found')
        return   

    return (source_uri, query_uri)

def zim_image_handler(root, uid, document):
    '''
    Generates a list of the links to all the downloaded images 
    present in the searched article from offline zim wikipedia
    '''
    # Kiwix image exceptions
    ignored_images = ["schools-wikipedia-logo", "checked-content"]
    document = BeautifulSoup(document)
    dir_path = os.path.join(root, uid, "images")

    logger.debug('image_handler: %s' % dir_path)

    if not os.path.exists(dir_path):
        os.makedirs(dir_path, 0777)

    image_list = []
    for image in document.findAll("img"):
        fail = False
        path = image['src']
        image_title = (os.path.split(path)[1])[:-4]
        image_ext = (os.path.split(path)[1])[-3:]

        source_path = _read_configuration()[0] + path[1:]
        local_path = os.path.join(dir_path, os.path.split(path)[1])

        if not (image_ext == 'gif' or image_title in ignored_images):
            image_contents = _open_url(source_path)
            if not image_contents is None:
                file = open(local_path, 'w+')
                file.write(image_contents)
                file.close()
                os.path.join(get_bundle_path(), 'examples')
                image_title = os.path.split(path)[1]
                shutil.copy2(local_path, os.path.join(get_bundle_path(), 'examples'))

                image_list.append((local_path, image_title, (os.path.join(get_bundle_path(), 
                                    'examples', (os.path.split(path)[1])))))

    return image_list

def image_handler(root, uid, document):
    """
        Takes a DITA article and downloads images referenced in it
        (finding all <image> tags).
        Attemps to fix incomplete paths using source url.
        @param document: DITA to work on
        @return: The document with image tags adjusted to point to local paths
    """
    document = BeautifulStoneSoup(document)
    dir_path =  os.path.join(root, uid, "images")

    logger.debug('image_handler: %s' % dir_path)

    if not os.path.exists(dir_path):
        os.makedirs(dir_path, 0777)

    for image in document.findAll("image"):
        fail = False
        path = image['href']
        if "#DEMOLIBRARY#" in path:
            path = path.replace("#DEMOLIBRARY#",
                    os.path.join(get_bundle_path(), 'examples'))
            image_title = os.path.split(path)[1]
            shutil.copyfile(path, os.path.join(dir_path, image_title))
        else:
            image_title = path.rsplit("/", 1)[-1]
            # attempt to fix incomplete paths
            if (not path.startswith("http://")) and document.source != None and document.source.has_key("href"):
                if path.startswith("//upload"):
                    path = 'http:' + path
                elif path.startswith("/"):
                    path = document.source['href'].rsplit("/", 1)[0] + path
                else:
                    path = document.source['href'].rsplit("/", 1)[0] + "/" + path
            logger.debug("Retrieving image: " + path)
            file = open(os.path.join(dir_path, image_title), 'wb')
            image_contents = _open_url(path)
            if image_contents == None:
                fail = True
            else:
                file.write(image_contents)
            file.close()
        #change to relative paths:
        if not fail:
            image['href'] = os.path.join(dir_path.replace(os.path.join(root, ""), "", 1), image_title)
            image['orig_href'] = path
        else:
            image.extract()

    return document.prettify()

def _open_url(url):
    """
        retrieves content from specified url
    """
    urllib._urlopener = _new_url_opener()
    try:
        logger.debug("opening " + url)
        logger.debug("proxies: " + str(proxies))
        doc = urllib.urlopen(url, proxies=proxies)
        output = doc.read()
        doc.close()
        logger.debug("url opened succesfully")
        return output
    except IOError, e:
        elogger.debug('_open_url: %s' % e)

class _new_url_opener(urllib.FancyURLopener):
    version = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1b2)" \
              "Gecko/20081218 Gentoo Iceweasel/3.1b2"

# http proxy

_proxy_file = os.path.join(os.path.split(os.path.split(__file__)[0])[0],
        'proxy.cfg')
_proxylist = {}

if os.access(_proxy_file, os.F_OK):
    proxy_file_handle = open(_proxy_file, "r")
    for line in proxy_file_handle.readlines():
        parts = line.split(':', 1)
        #logger.debug("setting " + parts[0] + " proxy to " + parts[1])
        _proxylist[parts[0].strip()] = parts[1].strip()
    proxy_file_handle.close()

if _proxylist:
    proxies = _proxylist
