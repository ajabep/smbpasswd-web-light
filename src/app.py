#!/usr/bin/env python3
"""smbpasswd-web is a simple web interface to smbpasswd.

The only purpose is to allow a user to change its samba password using a browser,
no user adding, no machine account, nothing, plain simple changing a password.
"""

import argparse
import enum
import json
import logging
import os
import secrets
import subprocess  # nosec: disable=B404
import sys
import textwrap
import traceback
import typing
import re

from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, request, Response, jsonify, render_template, abort, redirect, url_for

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ADDRESS = '0.0.0.0'  # nosec: disable=104
DEFAULT_PORT = 8080
DEFAULT_PROTO = 'http'

app = Flask(__name__)
app.secret_key = secrets.token_hex()

SMB_USERNAME_VALIDATOR = re.compile('^[a-zA-Z0-9]{1,256}$')


@enum.unique
class APIResponseType(enum.IntEnum):
    """Response type"""
    SUCCESS = 0
    CLIENT_ERROR = 1
    SERVER_ERROR = 2


@enum.unique
class APIClientErrorCode(enum.IntEnum):
    """Client error code"""
    UNKNOWN_ERROR = -1
    PASSWORDS_DIFFERENT = 0
    INVALID_FIELDS = 2


@enum.unique
class APIServerErrorCode(enum.IntEnum):
    """Server error code"""
    UNKNOWN_ERROR = -1
    TIMEOUT = 0
    SMBPASSWD_ERROR = 1
    NT_STATUS_ACCESS_DENIED = 2
    NT_STATUS_ACCOUNT_DISABLED = 3
    NT_STATUS_ACCOUNT_LOCKED_OUT = 4
    NT_STATUS_ACCOUNT_RESTRICTION = 5
    NT_STATUS_INVALID_ACCOUNT_NAME = 6
    NT_STATUS_NAME_TOO_LONG = 7
    NT_STATUS_PASSWORD_EXPIRED = 8


def api_response(data: dict, response_type: APIResponseType = APIResponseType.SUCCESS) -> Response:
    """Return a Response returning a client error"""
    return jsonify({
        'type': response_type,
        'data': data
    })


def api_client_error(error_code: APIClientErrorCode) -> Response:
    """Return a Response returning a client error"""
    return api_response(
        response_type=APIResponseType.CLIENT_ERROR,
        data={
            'error_code': error_code
        }
    )


def api_server_error(error_code: APIServerErrorCode) -> Response:
    """Return a Response returning a server error"""
    return api_response(
        response_type=APIResponseType.SERVER_ERROR,
        data={
            'error_code': error_code
        }
    )


def smbpasswd(username: str, old_password: str, new_password: str) \
        -> typing.Optional[APIServerErrorCode]:
    """Instantiate smbpasswd"""
    executable = "/usr/bin/smbpasswd"
    command = [
        executable,
        "-s",
        "-r",
        app.config['REMOTE_ADDR'],
        "-U",
        username
    ]
    input_param = [
        old_password,
        new_password,
        new_password
    ]

    try:
        logging.debug("Will execute '%s'", "' '".join(command))
        with subprocess.Popen(
            command,
            executable=executable,
            shell=False,  # nosec: disable=B603

            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ) as proc:
            stdout, stderr = proc.communicate(
                input=('\n'.join(input_param) + '\n').encode('ascii'),
                timeout=60
            )
            logging.debug("Return code for user %s = %s", username, proc.returncode)
            logging.debug("Stdout for user %s = %s", username, stdout)
            logging.debug("Stderr for user %s = %s", username, stderr)

            if proc.returncode == 0:
                logging.info("Return code for user %s = 0 ; SUCCESS!", username)
                return None

            stderr = stderr.strip()

            equivalents = {
                b'NT_STATUS_LOGON_FAILURE': APIServerErrorCode.NT_STATUS_ACCESS_DENIED,
                b'NT_STATUS_NO_SUCH_USER': APIServerErrorCode.NT_STATUS_ACCESS_DENIED,
                b'NT_STATUS_ACCESS_DENIED': APIServerErrorCode.NT_STATUS_ACCESS_DENIED,
            }

            for ex in APIServerErrorCode:
                if stderr.endswith(ex.name.encode('ascii')):
                    return ex

            for equivalent, val in equivalents.items():
                if stderr.endswith(equivalent):
                    return val

            return APIServerErrorCode.SMBPASSWD_ERROR

    except TimeoutError:
        proc.kill()
        logging.info("Timeout for user %s", username)
        logging.debug("Return code for user %s = %s", username, proc.returncode)
        return APIServerErrorCode.TIMEOUT

    except subprocess.SubprocessError:
        logging.error(
            "Unknown error during changing password for user %s : %s",
            username,
            '\n'.join(traceback.format_exc())
        )
        traceback.print_exc(file=sys.stderr)
        return APIServerErrorCode.UNKNOWN_ERROR


@app.context_processor
def inject_data() -> dict:
    """Inject global variables in templates"""
    return {
        'flask_data': {
            'pages': {
                index.__name__: 'Home',
                changepasswd.__name__: 'Password change',
            }
        }
    }


@app.before_request
def force_hostname():
    """Force the usage of the right hostname"""
    if request.host != app.config['HOSTNAME']:
        logging.warning("Just seen a request asking for '%s', expecting the hostname '%s'",
                        request.host, app.config['HOSTNAME'])
        abort(404)


@app.after_request
def security_headers(response: Response) -> Response:
    """Setup some security headers if not already present"""
    # pylint: disable=line-too-long
    headers = {
        'Content-Security-Policy': "default-src 'self'; "
                                   "img-src 'self' data:; "
                                   "font-src 'self' cdn.jsdelivr.net; "
                                   "style-src-elem 'self' cdn.jsdelivr.net; "
                                   "script-src 'self' 'sha384-fbbOQedDUMZZ5KreZpsbe1LCZPVmfTnH7ois6mU1QK+m14rQ1l2bGBq41eYeM/fS'; "  # noqa=E501
                                   "object-src 'none'; base-uri 'none'; sandbox allow-forms "
                                   "allow-scripts allow-same-origin; form-action 'self'; "
                                   "frame-ancestors 'none'",
        'X-Content-Type-Options': 'nosniff',
        'Referer': 'no-referrer',
        'Permissions-Policy': 'accelerometer=(), ambient-light-sensor=(), autoplay=(), '
                              'battery=(), camera=(), display-capture=(), document-domain=(), '
                              'encrypted-media=(), execution-while-not-rendered=(), '
                              'execution-while-out-of-viewport=(), fullscreen=(), gamepad=(), '
                              'geolocation=(), gyroscope=(), hid=(), identity-credentials-get=(), '
                              'idle-detection=(), local-fonts=(), magnetometer=(), microphone=(), '
                              'midi=(), payment=(), picture-in-picture=(), '
                              'publickey-credentials-create=(), publickey-credentials-get=(), '
                              'screen-wake-lock=(), serial=(), speaker-selection=(), '
                              'storage-access=(), usb=(), web-share=(), xr-spatial-tracking=()'
    }
    for h_name, h_value in headers.items():
        if response.headers.get(h_name) is None:
            response.headers[h_name] = h_value
    return response


@app.get("/robots.txt")
def robotstxt():
    """Robots.txt handler/generator"""
    return Response(
        textwrap.dedent(
            # pylint: disable=line-too-long
            '''\
            # Stop all search engines from crawling this site
            User-agent: *
            Disallow: /
            '''
        ),
        mimetype='text/plain',
        content_type='text/plain; charset=utf-8'
    )


@app.get("/.well-known/change-password")
def password_changer_redirector():
    """https://w3c.github.io/webappsec-change-password-url/"""
    return redirect(url_for('changepasswd'), code=302)


@app.get("/.well-known/security.txt")
def securitytxt():
    """Security.txt handler/generator"""
    return Response(
        textwrap.dedent(
            # pylint: disable=line-too-long
            '''\
            Contact: https://github.com/ajabep/smbpasswd-web-light/blob/main/SECURITY.md
            Expires: 2023-12-31T23:00:00.000Z
            Acknowledgments: https://github.com/ajabep/smbpasswd-web-light/blob/main/SECURITY.md#hall-of-fame
            Preferred-Languages: en, fr
            '''
        ),
        mimetype='text/plain',
        content_type='text/plain; charset=utf-8'
    )


@app.get("/")
def index() -> Response:
    """List of services"""
    # While we don't have any other service, redirect users to the only one
    return redirect(url_for('changepasswd'), code=302)
    # return render_template('index.html')


@app.get("/change-password")
def changepasswd() -> str:
    """Form to change the passwd"""
    return render_template('change_passwd.html')


@app.post('/api/changepasswd')
def api_changepasswd() -> Response:
    """Endpoint to change the passwd"""
    data = json.loads(request.json)
    username = str(data['username']) or ''
    oldpasswd = str(data['password']) or ''
    passwd = str(data['newpassword']) or ''
    confirmpasswd = str(data['confirmpassword']) or ''

    if passwd != confirmpasswd:
        return api_client_error(APIClientErrorCode.PASSWORDS_DIFFERENT)

    if '' in [username, oldpasswd, passwd, confirmpasswd]:
        return api_client_error(APIClientErrorCode.INVALID_FIELDS)

    if len(username) < 1 or len(username) > 256 or \
            SMB_USERNAME_VALIDATOR.match(username) is None:
        return api_client_error(APIClientErrorCode.INVALID_FIELDS)

    if len(passwd) < 15 or len(passwd) > 127:
        return api_client_error(APIClientErrorCode.INVALID_FIELDS)

    logging.info("Trying to change the password of %s", username)

    ret_code = smbpasswd(username, oldpasswd, passwd)
    if ret_code is None:
        # Success
        return api_response({})
    return api_server_error(ret_code)


def main():
    """Parse CLI arguments and start the server"""
    parser = argparse.ArgumentParser(
        description="Web interface to change samba user's password",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--url", help="URI behind which the web page is available")
    parser.add_argument("-v", "--verbose", help="Log HTTP requests", action="count", default=0)
    parser.add_argument(
        "--unsafe-development-mode",
        help="UNSAFE; Enable the development mode. DO NOT USE THIS IN PRODUCTION",
        action="store_true",
        default=False,
        dest="devmode"
    )
    parser.add_argument("remote", help="Address of the remote SMB server")
    parser.add_argument("hostname", help="The hostname that requests are supposed to use")

    # Parse arguments
    args = parser.parse_args()

    print(f'Verbosity: {args.verbose}')
    if args.verbose >= 2:
        logging.basicConfig(level=logging.NOTSET)
    elif args.verbose == 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    app.config['REMOTE_ADDR'] = args.remote
    app.config['HOSTNAME'] = args.hostname

    logging.info("Listening on: %s://%s:%s/", DEFAULT_PROTO, DEFAULT_ADDRESS, DEFAULT_PORT)
    if args.url is not None:
        logging.info("If your redirection works correctly, it should be available using: %s",
                     args.url)

    if args.devmode:
        app.config['DEVMODE'] = True
        app.run(
            debug=args.verbose >= 1,
            host=DEFAULT_ADDRESS,
            port=DEFAULT_PORT
        )
    else:
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_host=1
        )


def create_app(argv) -> Flask:
    """Create the right app object for WSGI server, and transforms the CLI arguments given as an
    argument to sys.argv"""
    sys.argv = argv.split(' ')
    main()
    return app


if __name__ == "__main__":
    main()
