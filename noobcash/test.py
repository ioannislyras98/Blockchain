from Crypto.Signature import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
import Crypto

key = RSA.generate(1024)

x = key.exportKey()
y = key.publickey().exportKey()

msg = Crypto.Random.get_random_bytes(16)
print(msg)

tmp = SHA256.new()
tmp.update(msg)
ff = RSA.import_key(x)
cipher = PKCS1_v1_5.new(ff)

txt = cipher.sign(tmp)
print(txt)

cipher2 = PKCS1_v1_5.new(RSA.import_key(y))
tst = cipher2.verify(tmp, txt)
print(tst)