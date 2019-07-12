# -*- coding: utf-8 -*-
import sys, traceback
import re, json, binascii, base64, hashlib

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from mutagen import mp3, flac, id3

key = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')

def parser(url):
    if 'event' in url:
        id = re.search(r'id=(\d+)', url).group(1)
        uid = re.search(r'uid=(\d+)', url).group(1)
        response = requests.get('https://music.163.com/event', params = {'id': id, 'uid': uid})
        data = re.search(r'<textarea.+id="event-data".*>([\s\S]+?)</textarea>', response.text).group(1)
        data = json.loads(data.replace('&quot;', '"'))
        data = json.loads(data['json'])
        if 'song' in data:
            return data['song']
        elif 'resource' in data and 'resourceInfo' in data['resource']:
            return json.loads(data['resource']['resourceInfo'])
        elif 'event' in data:
            data = json.loads(data['event']['json'])
            return data['song']
    elif 'album' in url:
        id = re.search(r'id=(\d+)', url).group(1)
        response = requests.get('https://music.163.com/api/album/' + id)
        data = json.loads(response.text)
        return {
            'album': data['album'],
            'artists': data['album']['artists']
        }

def marker(path, song, id = None):
    def streamify(file):
        with file:
            return file.read()

    def embed(item, content, type):
        item.encoding = 0
        item.type = type
        item.mime = 'image/png' if content[0:4] == binascii.a2b_hex('89504E47') else 'image/jpeg'
        item.data = content

    format = 'flac' if open(path, 'rb').read(4) == binascii.a2b_hex('664C6143') else 'mp3'
    audio = mp3.EasyMP3(path) if format == 'mp3' else flac.FLAC(path)
    
    meta = {
        'album': song['album']['name'],
        'albumId': song['album']['id'],
        'albumPic': song['album']['picUrl'],
        'albumPicDocId': song['album']['pic'] if 'pic' in song['album'] else re.search(r'/(\d+)\.\w+$', song['album']['picUrl']).group(1),
        'alias': song['alias'] if 'alias' in song else [],
        'artist': [[artist['name'], artist['id']] for artist in song['artists']],
        'musicId': id if id else song['id'],
        'musicName': song['name'] if 'name' in song else audio['title'][0],
        'mvId': song['mvid'] if 'mvid' in song else 0,
        'transNames': [],
        'format': format,
        'bitrate': audio.info.bitrate,
        'duration': int(audio.info.length * 1000),
        'mp3DocId': hashlib.md5(streamify(open(path, 'rb'))).hexdigest()
    }

    cryptor = AES.new(key, AES.MODE_ECB)
    identification = 'music:' + json.dumps(meta)
    identification = '163 key(Don\'t modify):' + base64.b64encode(cryptor.encrypt(pad(identification.encode('utf8'), 16))).decode('utf8')

    audio.delete()
    audio['title'] = meta['musicName']
    audio['album'] = meta['album']
    audio['artist'] = '/'.join([artist[0] for artist in meta['artist']])

    if format == 'flac':
        audio['description'] = identification
    else:
        audio.tags.RegisterTextKey('comment', 'COMM')
        audio['comment'] = identification
    audio.save()

    data = requests.get(meta['albumPic'] + '?param=300y300').content
    if format == 'flac':
        audio = flac.FLAC(path)
        image = flac.Picture()
        embed(image, data, 3)
        audio.clear_pictures()
        audio.add_picture(image)
    elif format == 'mp3':
        audio = mp3.MP3(path)
        image = id3.APIC()
        embed(image, data, 6)
        audio.tags.add(image)
    audio.save()

def watcher(path):
    if open(path, 'rb').read(4) == binascii.a2b_hex('664C6143'):
        audio = flac.FLAC(path)
        identification = audio['description']
    else:
        audio = mp3.MP3(path)
        identification = [text for item in audio.tags.getall('COMM') for text in item.text]
    identification = max(identification, key = len)

    identification = base64.b64decode(identification[22:])
    cryptor = AES.new(key, AES.MODE_ECB)
    meta = unpad(cryptor.decrypt(identification), 16).decode('utf8')
    meta = json.loads(meta[6:])
    print(json.dumps(meta, ensure_ascii = False))
    return meta

if __name__ == '__main__':
    try:
        marker(sys.argv[1], parser(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None) if len(sys.argv) > 2 else watcher(sys.argv[1])
    except Exception:
        traceback.print_exc()