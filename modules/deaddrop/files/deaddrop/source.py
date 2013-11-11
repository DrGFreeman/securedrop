# -*- coding: utf-8 -*-
import os
from datetime import datetime
import uuid
from functools import wraps

from flask import (Flask, request, render_template, session, redirect, url_for,
    flash, abort, g)
from flask_wtf.csrf import CsrfProtect

import config, version, crypto, store, background

app = Flask(__name__, template_folder=config.SOURCE_TEMPLATES_DIR)
app.secret_key = config.SECRET_KEY

app.jinja_env.globals['version'] = version.__version__

def logged_in():
  if 'logged_in' in session: return True

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not logged_in():
            return redirect(url_for('lookup'))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def setup_g():
  """Store commonly used values in Flask's special g object"""
  if logged_in():
    g.flagged = session['flagged']
    g.codename = session['codename']
    g.sid = crypto.shash(g.codename)
    g.loc = store.path(g.sid)

@app.after_request
def no_cache(response):
  """Minimize potential traces of site access by telling the browser not to
  cache anything"""
  no_cache_headers = {
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '-1',
      }
  for header, header_value in no_cache_headers.iteritems():
    response.headers.add(header, header_value)
  return response

@app.route('/')
def index():
  return render_template('index.html')

@app.route('/generate', methods=('GET', 'POST'))
def generate():
  number_words = 8
  if request.method == 'POST':
    number_words = int(request.form['number-words'])
    if number_words not in range(4, 11): abort(403)
  session['codename'] = crypto.genrandomid(number_words)
  return render_template('generate.html', codename=session['codename'])

@app.route('/create', methods=['POST'])
def create():
  sid = crypto.shash(session['codename'])
  if os.path.exists(store.path(sid)):
    # if this happens, we're not using very secure crypto
    store.log("Got a duplicate ID '%s'" % sid)
  else:
    os.mkdir(store.path(sid))
  session['logged_in'] = True
  return redirect(url_for('lookup'))

@app.route('/lookup', methods=('GET',))
@login_required
def lookup():
  msgs = []
  for fn in os.listdir(g.loc):
    if fn.startswith('reply-'):
      msgs.append(dict(
        id=fn,
        date=str(datetime.fromtimestamp(os.stat(store.path(g.sid, fn)).st_mtime)),
        msg=crypto.decrypt(g.sid, g.codename, file(store.path(g.sid, fn)).read())
      ))
  return render_template('lookup.html', codename=g.codename, msgs=msgs)

@app.route('/submit', methods=('POST',))
@login_required
def submit():
  msg = request.form['msg']
  fh = request.files['fh']
  if msg:
    msg_loc = store.path(g.sid, '%s_msg.gpg' % uuid.uuid4())
    crypto.encrypt(config.JOURNALIST_KEY, msg, msg_loc)
    flash("Thanks! We received your message.", "notification")
  if fh:
    file_loc = store.path(g.sid, "%s_doc.gpg" % uuid.uuid4())
    # TODO - retain original filename
    crypto.encrypt(config.JOURNALIST_KEY, fh, file_loc)
    flash("Thanks! We received your document '%s'."
        % fh.filename or '[unnamed]', "notification")

  # helper function to generate a keypair asynchronously
  def async_genkey(sid, codename):
    with app.app_context():
      background.execute(lambda: crypto.genkeypair(sid, codename))

  # Generate a keypair to encrypt replies from the journalist
  # Only do this if the journalist has flagged the source as one
  # that they would like to reply to. (Issue #140.)
  if not crypto.getkey(g.sid) and g.flagged:
    flash("A journalist has indicated that they would like to reply to you. Please check back shortly for their reply.")
    async_genkey(g.sid, g.codename)

  return redirect(url_for('lookup'))

@app.route('/delete', methods=('POST',))
@login_required
def delete():
  msgid = request.form['msgid']
  assert '/' not in msgid
  potential_files = os.listdir(g.loc)
  if msgid not in potential_files: abort(404) # TODO are the checks necessary?
  crypto.secureunlink(store.path(g.sid, msgid))
  flash("Reply deleted.", "notification")

  return redirect(url_for('lookup'))

def valid_codename(codename):
  return os.path.exists(store.path(crypto.shash(codename)))

@app.route('/login', methods=('GET', 'POST'))
def login():
  if request.method == 'POST':
    codename = request.form['codename']
    if valid_codename(codename):
      session.update(codename=codename, logged_in=True)
      return redirect(url_for('lookup'))
    else:
      flash("Sorry, that is not a recognized codename.", "error")
  return render_template('login.html')

@app.route('/howto-disable-js')
def howto_disable_js():
    return render_template("howto-disable-js.html")

@app.errorhandler(404)
def page_not_found(error):
  return render_template('notfound.html'), 404

if __name__ == "__main__":
  # TODO: make sure this gets run by the web server
  CsrfProtect(app)
  app.run(debug=True, port=8080)
