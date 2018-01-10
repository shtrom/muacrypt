from __future__ import print_function, unicode_literals
import os
import re
import six
from muacrypt import mime


def test_help(cmd):
    cmd.run_ok([], """
        *init*
        *make-header*
        *export-public-key*
        *export-secret-key*
    """)
    cmd.run_ok(["--help"], """
        *access and manage*
    """)


def test_init_help(cmd):
    cmd.run_ok(["init", "--help"], """
        *init*
    """)


def test_init(mycmd):
    mycmd.run_ok(["init"], """
            *account*initialized*
            *gpgmode*own*
    """)
    mycmd.run_fail(["init"], """
            *account*exists*
    """)
    mycmd.run_ok(["init", "--replace"], """
            *deleting account dir*
            *account*initialized*
    """)


def test_init_and_make_header(mycmd):
    mycmd.run_fail(["make-header", "xyz"], """
        *AccountManager*not initialized*
    """)
    adr = "x@yz.org"
    mycmd.run_ok(["init"])
    out = mycmd.run_ok(["make-header", adr])
    d = mime.parse_one_ac_header_from_string(out)
    assert "prefer-encrypt" not in out
    assert "type" not in out
    assert d["addr"] == adr
    out2 = mycmd.run_ok(["make-header", adr])
    assert out == out2


def test_init_and_make_header_with_envvar(cmd, tmpdir):
    with tmpdir.as_cwd():
        os.environ["MUACRYPT_BASEDIR"] = "."
        test_init_and_make_header(cmd)


def test_exports_and_status_plain(mycmd):
    mycmd.run_ok(["init"])
    out = mycmd.run_ok(["export-public-key"])
    check_ascii(out)
    out = mycmd.run_ok(["export-secret-key"])
    check_ascii(out)
    out = mycmd.run_ok(["status"], """
        account-dir:*
        *account*default*uuid*
        *prefer-encrypt*nopreference*
        *own-keyhandle:*
    """)


def check_ascii(out):
    if isinstance(out, six.text_type):
        out.encode("ascii")
    else:
        out.decode("ascii")


class TestProcessIncoming:
    def test_process_incoming(self, mycmd, datadir):
        mycmd.run_ok(["init", "--no-account"])
        mycmd.run_ok(["add-account", "account1", "--email-regex=some@example.org"])
        mail = datadir.read("rsa2048-simple.eml")
        mycmd.run_fail(["process-incoming"], """
            *AccountNotFound*bob@testsuite.autocrypt.org*
        """, input=mail)

        msg = mime.parse_message_from_string(mail)
        msg.replace_header("Delivered-To", "some@example.org")
        newmail = msg.as_string()
        out = mycmd.run_ok(["process-incoming"], """
            *processed*account*account1*
        """, input=newmail)

        # now export the public key
        m = re.search(r'key=(\w+)', out)
        keyhandle, = m.groups()
        mycmd.run_ok(["export-public-key", "--account=account1", keyhandle])
        mycmd.run_ok(["status"])

    def test_process_incoming_no_autocrypt(self, mycmd, datadir):
        mycmd.run_ok(["init", "--no-account"])
        mycmd.run_ok(["add-account", "account1", "--email-regex=b@b.org"])
        msg = mime.gen_mail_msg(From="Alice <a@a.org>", To=["b@b.org"], _dto=True)
        mycmd.run_ok(["process-incoming"], """
            *processed*account1*no*Autocrypt*header*
        """, input=msg.as_string())


class TestAccountCommands:
    def test_add_list_del_account(self, mycmd):
        mycmd.run_ok(["init", "--no-account"])
        mycmd.run_ok(["status"], """
            *no accounts configured*
        """)
        mycmd.run_ok(["add-account", "home", "--email-regex=home@example.org"], """
            *account added*home*
        """)
        mycmd.run_ok(["status"], """
            *account*home*
            *home@example.org*
        """)
        mycmd.run_ok(["del-account", "home"])
        mycmd.run_ok(["status"], """
            *no accounts configured*
        """)

    def test_modify_account_prefer_encrypt(self, mycmd):
        mycmd.run_ok(["init"])
        mycmd.run_ok(["status"], """
            *account*default*
        """)
        mycmd.run_ok(["mod-account", "default", "--prefer-encrypt=mutual"], """
            *account modified*default*
            *email?regex*.**
            *prefer-encrypt*mutual*
        """)
        mycmd.run_ok(["mod-account", "default", "--email-regex=xyz"], """
            *account modified*default*
            *email?regex*xyz*
            *prefer-encrypt*mutual*
        """)

        mycmd.run_ok(["mod-account", "default", "--prefer-encrypt=nopreference"], """
            *account modified*default*
            *email?regex*xyz*
            *prefer-encrypt*nopreference*
        """)

    def test_init_existing_key_native_gpg(self, mycmd, monkeypatch, bingpg, gpgpath):
        adr = "x@y.org"
        keyhandle = bingpg.gen_secret_key(adr)
        monkeypatch.setenv("GNUPGHOME", bingpg.homedir)
        mycmd.run_ok(["init", "--no-account"])
        mycmd.run_ok(["add-account", "home", "--use-key", adr,
                      "--gpgbin=%s" % gpgpath, "--use-system-keyring"], """
                *gpgmode*system*
                *gpgbin*{}*
                *own-keyhandle*{}*
        """.format(gpgpath, keyhandle))
        mycmd.run_ok(["make-header", adr], """
            *Autocrypt*addr=x@y.org*
        """)

    def test_test_email(self, mycmd):
        mycmd.run_ok(["init", "--no-account"])
        mycmd.run_ok(["add-account", "home", "--email-regex=(home|office)@example.org"])
        mycmd.run_ok(["test-email", "home@example.org"])
        mycmd.run_ok(["test-email", "office@example.org"])
        mycmd.run_fail(["test-email", "xhome@example.org"], """
            *AccountNotFound*xhome@example.org*
        """)


class TestProcessOutgoing:
    def test_simple(self, mycmd, gen_mail):
        mycmd.run_ok(["init"])
        mail = gen_mail()
        out1 = mycmd.run_ok(["process-outgoing"], input=mail.as_string())
        m = mime.parse_message_from_string(out1)
        assert len(m.get_all("Autocrypt")) == 1
        found_header = "Autocrypt: " + m["Autocrypt"]
        gen_header = mycmd.run_ok(["make-header", "a@a.org"])
        x1 = mime.parse_one_ac_header_from_string(gen_header)
        x2 = mime.parse_one_ac_header_from_string(found_header)
        assert x1 == x2

    def test_matching_account(self, mycmd, gen_mail):
        mycmd.run_ok(["init", "--no-account"])
        mycmd.run_ok(["add-account", "account1", "--email-regex=account1@a.org"])
        mail = gen_mail(From="x@y.org")
        # mycmd.run_fail(["process-outgoing"], input=mail.as_string(), fnl="""
        #     *AccountNotFound*x@y.org*
        # """)
        out0 = mycmd.run_ok(["process-outgoing"], input=mail.as_string())
        assert "Autocrypt" not in out0

        mail = gen_mail(From="account1@a.org")
        out1 = mycmd.run_ok(["process-outgoing"], input=mail.as_string())
        msg2 = mime.parse_message_from_string(out1)
        assert "account1@a.org" in msg2["Autocrypt"]

    def test_simple_dont_replace(self, mycmd, gen_mail):
        mycmd.run_ok(["init"])
        mail = gen_mail()
        gen_header = mycmd.run_ok(["make-header", "x@x.org"])
        mail.add_header("Autocrypt", gen_header)

        out1 = mycmd.run_ok(["process-outgoing"], input=mail.as_string())
        m = mime.parse_message_from_string(out1)
        assert len(m.get_all("Autocrypt")) == 1
        x1 = mime.parse_ac_headervalue(m["Autocrypt"])
        x2 = mime.parse_ac_headervalue(gen_header)
        assert x1 == x2

    def test_sendmail(self, mycmd, gen_mail, popen_mock):
        mycmd.run_ok(["init"])
        mail = gen_mail().as_string()
        pargs = ["-oi", "b@b.org"]
        mycmd.run_ok(["sendmail", "-f", "--"] + pargs, input=mail)
        assert len(popen_mock.calls) == 1
        call = popen_mock.pop_next_call()
        for x in pargs:
            assert x in call.args
        # make sure unknown option is passed to pipe
        assert "-f" in call.args
        out_msg = mime.parse_message_from_string(call.input)
        assert "Autocrypt" in out_msg, out_msg.as_string()

    def test_sendmail_no_account(self, mycmd, gen_mail, popen_mock):
        mycmd.run_ok(["init"])
        mycmd.run_ok(["mod-account", "default", "--email-regex", "123123"])
        mail = gen_mail().as_string()
        pargs = ["-oi", "b@b.org"]
        mycmd.run_ok(["sendmail", "-f", "--"] + pargs, input=mail)
        assert len(popen_mock.calls) == 1
        call = popen_mock.pop_next_call()
        for x in pargs:
            assert x in call.args
        # make sure unknown option is passed to pipe
        assert "-f" in call.args
        out_msg = mime.parse_message_from_string(call.input)
        assert "Autocrypt" not in out_msg, out_msg.as_string()

    def test_sendmail_fails(self, mycmd, gen_mail, popen_mock):
        mycmd.run_ok(["init"])
        mail = gen_mail().as_string()
        pargs = ["-oi", "b@b.org"]
        popen_mock.mock_next_call(ret=2)
        mycmd.run_fail(["sendmail", "-f", "--", "--qwe"] + pargs, input=mail, code=2)
        assert len(popen_mock.calls) == 1
        call = popen_mock.pop_next_call()
        for x in pargs:
            assert x in call.args
        # make sure unknown option is passed to pipe
        assert "-f" in call.args
        assert "--qwe" in call.args
