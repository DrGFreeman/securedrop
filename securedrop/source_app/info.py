# -*- coding: utf-8 -*-
import flask
from flask import Blueprint, render_template, send_file, current_app

from io import BytesIO  # noqa

from sdconfig import SDConfig


def make_blueprint(config: SDConfig) -> Blueprint:
    view = Blueprint('info', __name__)

    @view.route('/tor2web-warning')
    def tor2web_warning() -> str:
        return render_template("tor2web-warning.html")

    @view.route('/use-tor')
    def recommend_tor_browser() -> str:
        return render_template("use-tor-browser.html")

    @view.route('/public-key')
    def download_journalist_pubkey() -> flask.Response:
        journalist_pubkey = current_app.crypto_util.gpg.export_keys(
            config.JOURNALIST_KEY)
        data = BytesIO(journalist_pubkey.encode('utf-8'))
        return send_file(data,
                         mimetype="application/pgp-keys",
                         attachment_filename=config.JOURNALIST_KEY + ".asc",
                         as_attachment=True)

    @view.route('/why-public-key')
    def why_download_journalist_pubkey() -> str:
        return render_template("why-public-key.html")

    return view
