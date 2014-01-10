import os
import sys
import fcntl
import random
from subprocess import Popen, PIPE
from datetime import datetime
from util import sha512b64 as genkey

class SymmetricEncrypter:
    """
    Symmetric encryption/decryption. Currently wraps OpenSSL's command line.
    """
    beginblock = "-----BEGIN MAILPILE ENCRYPTED DATA-----"
    endblock = "-----END MAILPILE ENCRYPTED DATA-----"
    defaultcipher = "aes-256-gcm"

    def __init__(self, secret=None):
        self.available = None
        self.binary = 'openssl'
        self.handles = {}
        self.pipes = {}
        self.fds = ["stdout", "stderr"]
        self.errors = []
        self.statuscallbacks = {}
        self.secret = secret

    def run(self, args=[], output=None, passphrase=None, debug=False):
        self.pipes = {}
        args.insert(0, self.binary)

        if debug:
            print "Running openssl as: %s" % " ".join(args)

        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)

        self.handles["stdout"] = proc.stdout
        self.handles["stderr"] = proc.stderr
        self.handles["stdin"] = proc.stdin

        if passphrase:
            self.handles["stdin"].write(passphrase + "\n")

        if output:
            self.handles["stdin"].write(output)

        self.handles["stdin"].close()

        retvals = dict([(fd, "") for fd in self.fds])
        while True:
            proc.poll()
            for fd in self.fds:
                try:
                    buf = self.handles[fd].read()
                except IOError:
                    continue
                if buf == "":
                    continue
                retvals[fd] += buf
            if proc.returncode is not None:
                break

        return proc.returncode, retvals

    def encrypt(self, data, cipher=None):
        if not cipher:
            cipher = self.defaultcipher
        nonce = genkey(str(random.getrandbits(512)))[:32].strip()
        enckey = genkey(self.secret, nonce)[:32].strip()
        params = ["enc", "-e", "-a", "-%s" % cipher, 
                  "-pass", "stdin",
                 ]
        retval, res = self.run(params, output=data, passphrase=enckey)
        ret = "%s\ncipher: %s\nnonce: %s\n\n%s\n%s" % (
            self.beginblock, cipher, nonce, res["stdout"], self.endblock)
        return ret

    def decrypt(self, data):
        try:
            head, enc, tail = data.split("\n\n")
            head = [h.strip() for h in head.split("\n")]
        except:
            try:
                head, enc, tail = data.split("\r\n\r\n")
                head = [h.strip() for h in head.split("\r\n")]
            except:
                raise ValueError("Not a valid OpenSSL encrypted block.")

        if (not head or not enc or not tail
                or head[0] != self.beginblock
                or tail.strip() != self.endblock):
            raise ValueError("Not a valid OpenSSL encrypted block.")

        try:
            headers = dict([l.split(': ', 1) for l in head[1:]])
        except:
            raise ValueError("Message contained invalid parameter.")

        cipher = headers.get('cipher', self.defaultcipher)
        nonce = headers.get('nonce')
        if not nonce:
            raise ValueError("Encryption nonce not known.")

        enckey = genkey(self.secret, nonce)[:32].strip()
        params = ["enc", "-d", "-a", "-%s" % cipher, 
                  "-pass", "stdin",
                 ]
        retval, res = self.run(params, output=enc, passphrase=enckey)
        return res["stdout"]

    def decrypt_fd(self, lines, fd):
        for line in fd:
            lines.append(line)
            if line.startswith(GPG_END_MESSAGE):
                break

        ret = self.decrypt("".join(lines))
        return ret.split("\n")


class EncryptedFile(object):
    def __init__(self, filename, secret, mode="w"):
        self.encrypter = SymmetricEncrypter(secret)
        self.filename = filename
        self.fd = open(fd, mode)

    def write(self, data):
        enc = self.encrypter.encrypt(data)
        self.fd.write(enc)

    def read(self):
        enc = self.fd.readlines()
        data = self.encrypter.decrypt(enc)

    def close(self):
        self.fd.close()


if __name__ == "__main__":
    s = SymmetricEncrypter("d3944bfea1e882dfc2e4878fa8905c6a2c")
    teststr = "Hello! This is a longish thing." * 50
    print "Example encrypted format:"
    print s.encrypt(teststr)
    if teststr == s.decrypt(s.encrypt(teststr)):
        print "Basic decryption worked"
    else:
        print "Encryption test failed"

    t0 = datetime.now()
    enc = s.encrypt(teststr)
    print "Speed test:"
    for i in range(5000):
        s.decrypt(enc)
        if i % 50 == 0:
            print "\r %-3d%% %s>" % (int(i / 50.0), "-" * (i//100)),
            sys.stdout.flush()
    t1 = datetime.now()
    print "\n5000 decrypt ops took %s => %s/op" % ((t1-t0), (t1-t0)/5000)
