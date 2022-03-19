from flask import Flask, request, send_file, redirect
import youtube_dl
import os
import glob
import time
from threading import Thread, local
from sanitize_filename import sanitize
from urllib.parse import quote

app = Flask('app')
app.debug = True

supported_formats = {
    "m_wmv": {
        "ext": "wmv",
        "cmd": "ffmpeg -y -i \"{0}\" -vf scale=w=320:h=240:force_original_aspect_ratio=decrease \"{1}\"",
        "desc": "Medium wmv (320 x 240)"
    },
    "s_wmv": {
        "ext": "wmv",
        "cmd": "ffmpeg -y -i \"{0}\" -filter:v fps=15 -ac 1 -b:v 200k -b:a 64k -vf scale=w=176:h=144:force_original_aspect_ratio=decrease \"{1}\"",
        "desc": "Small wmv (176 x 144)" #
    },
    "wii": {
        "ext": "flv",
        "cmd": "ffmpeg -y -i \"{0}\" -c:v flv -ar 22050 -crf 28 \"{1}\"",
        "desc": "Flash for Wii browser",
        "id": True
    },
    "w128": {
        "ext": "wma",
        "cmd": "ffmpeg -i \"{0}\" -ac 2 -ar 44100 -acodec wmav2 -ab 128k \"{1}\"",
        "desc": "128kbps wma [transcoded]",
        "audio": True
    },
    "128": {
        "ext": "mp3",
        "cmd": "ffmpeg -i \"{0}\" -vn -ar 44100 -ac 2 -ab 128k -f mp3 \"{1}\"",
        "desc": "128kbps mp3 [transcoded]",
        "audio": True
    },
    "bestaudio": {
        "ext": "m4a",
        "desc": "bestaudio m4a [broken rn?]",
        "audio": True
    },
}

listed_extensions = ['.bestaudio.m4a']

for f in supported_formats:
    if (not supported_formats[f]['ext'] in listed_extensions) and supported_formats[f]['ext'] != 'm4a':
        listed_extensions.append(supported_formats[f]['ext'])
        
processing_queue = []

def gen_formats():
    e = '\n'
    for form in supported_formats:
        i = ''
        if 'id' in supported_formats[form]:
            i = ' id="{0}"'.format(form)
        e += '<option value="{0}"{2}>{1}</option>\n'.format(form, supported_formats[form]['desc'], i)
    return e

front = '''
<html>
	<head>
		<title>winvid2</title>{1}
	</head>
	<body>
		<b>winvid2</b><br>
		Download and watch videos on old systems!<br>
		
		<form action="/" method="POST">
		<input type="text" name="video" placeholder="Enter a video URL or query..">
		<input type="submit" value="Get video">
		<br>
		<select name="format">
			{2}
		</select>
		</form>

        <script>
            if (navigator.userAgent.indexOf("wii") > -1) 
                document.getElementById("wii").selected = true
        </script>

		{0}
	</body>
</html>
'''
videoplayer = """<html>
<head>
<title>JW Flash FLV Player</title>
</head>
<body bgcolor="black">


<object type="application/x-shockwave-flash" data="/static/flvplayer.swf?file={0}" width="100%" height="100%" wmode="transparent">
  <param name="movie" value="/static/flvplayer.swf?file={0}" />
  <param name="wmode" value="fullscreen" />
</object>


</body>
</html>
"""

@app.route('/cache/', defaults={'req_path': ''})
@app.route('/cache/<path:req_path>')
def dir_listing(req_path):
    req_path = 'cache/{0}'.format(req_path)
    if os.path.isfile(req_path):
        return send_file(req_path)
    return "Nope"


@app.route('/cache/clear')
def clear_cache():
    for f in glob.glob('cache/*.*'):
        os.remove(f)
    return 'Okay...'

@app.route('/delete', methods=["GET", "POST"])
def delete_a_file():
    print(request.args['file'])
    if not request.args['file'].endswith('.mp4'):
        os.remove('cache/{0}'.format(request.args['file']))
    return redirect('/', 302)

@app.route('/play', methods=["GET"])
def stream_video():
	print(request.args['file'])
	if request.args['file'].endswith('.flv'):
		return videoplayer.format('/cache/' + request.args['file'])
	else:	
		return redirect('/cache/' + request.args['file'], 302)

@app.route('/', methods=["GET", "POST"])
def frontpage():
    msg = 'Type a search term (more specific is better) or video url and it will show in the list of cached videos below.<br><sub>Note that for now, cached videos are public until deleted or cleared.</sub>'
    if 'video' in request.form:
        fileformat = 'med_wmv'
        if request.form['format'] in supported_formats.keys():
            fileformat = request.form['format']

        ydlopts = {'outtmpl': '%(id)s.%(ext)s', 'default_search': 'ytsearch', 'format': 'mp4'}
        ydl = youtube_dl.YoutubeDL(ydlopts)
        query = request.form['video']
        dic = ydl.extract_info(query, False)

        dl_ext = 'mp4'
        if 'audio' in supported_formats[fileformat]:
            dl_ext = 'm4a'
            ydlopts['format'] = "bestaudio[ext=m4a]"
        if 'entries' in dic:
            filename = 'cache/' + sanitize("{0}_{1}.{2}.{3}".format(dic['entries'][0]['title'], dic['entries'][0]['id'], fileformat, dl_ext))
        else:
            filename = 'cache/' + sanitize("{0}_{1}.{2}.{3}".format(dic['title'], dic['id'], fileformat, dl_ext))
        ydlopts['outtmpl'] = filename
        ydl = youtube_dl.YoutubeDL(ydlopts)
        ydl.download([request.form['video']])  

        if 'cmd' in supported_formats[fileformat]:
            source = filename
            output = filename.replace('.{0}'.format(dl_ext), '.{0}'.format(supported_formats[fileformat]['ext']))
            def process_video():
                cmd = supported_formats[fileformat]['cmd'].format(source, output)
                print(cmd)

                processing_queue.append(output)
                os.system(cmd)
                processing_queue.remove(output)

                os.remove(source)

            thread = Thread(target=process_video)
            thread.start()

            while (not os.path.isfile(output)) or time.sleep(1):
                pass

        return redirect('/', 302)

    msg += "<ul>"

    autorefresh = ''

    files = []
    for ext in listed_extensions:
        files.extend(glob.glob('cache/*.{0}'.format(ext)))

    for f in files:
        if os.path.isfile(f):
            if f in processing_queue:
                msg += "<li><img src=\"static/spin.gif\"> <i>Processing: {0} ({1})</i></li>".format(
                    f.replace("cache/", ""), "{0} MB".format(
                        round(os.path.getsize(f) / (1000 * 1000), 2)))
                autorefresh = "<meta http-equiv=\"refresh\" content=\"10\">"
            else:
                path = "/cache/{0}"
                if f.endswith('.flv'):
                    path = '/play?file={0}'
                path = path.format(f.replace('cache/', ''))
                msg += "<li><a href=\"/delete?file={0}\" title=\"Delete this download\"><img alt=\"Delete this download\" src=\"static/delete.png\"></a><img alt=\"Download video\" src=\"static/control_play.png\"><a href=\"{2}\">{3}</a>  <i>{1}</i></li>".format(
                    quote(f.replace("cache/", "")), "{0} MB".format(
                        round(os.path.getsize(f) / (1000 * 1000), 2)), path, f.replace("cache/", ""))

    msg += "</ul>"
    return front.format(msg, autorefresh, gen_formats())


app.run(host='0.0.0.0', port=8080)