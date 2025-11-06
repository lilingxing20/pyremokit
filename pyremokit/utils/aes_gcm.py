# -*- coding:utf-8 -*-

import os
import time

from base64 import b64encode, b64decode
from Crypto.Cipher import AES


class AESGCMCipher:
    '''
    AES/GCM/NoPadding
    '''
    # string encode/decode encoding
    encoding_utf8 = 'utf-8'
    # The secret key must be 16 (e.g. *AES-128*), 24 (e.g. *AES-192*) or 32 (e.g. *AES-256*) bytes long.
    KEY = os.getenv("PYREMOKIT_AES_GCM_KEY", "L+eubUqRen2P2BlL6ekjPGurxxxbg5WeXjX7rmNx79E=")
    # The IV(Initialisation Vector) no restrictions on its length.
    # For GCM a 12 byte IV is strongly suggested as other IV lengths will require additional calculations.
    # https://crypto.stackexchange.com/questions/41601/aes-gcm-recommended-iv-size-why-12-bytes
    IV_LEN = 12
    # The received mac tag must be in the range 4..16
    TAG_LEN = 16

    @classmethod
    def aes_gcm_encrypt(cls, plaintext, secret_key=None, iv=None):
        '''
        使用AES-GCM算法加密
        '''
        secret_key = b64decode(secret_key or cls.KEY)
        nonce = iv or os.urandom(cls.IV_LEN)
        aes_cipher = AES.new(secret_key, AES.MODE_GCM, nonce)
        ciphertext, auth_tag = aes_cipher.encrypt_and_digest(plaintext.encode(cls.encoding_utf8))
        res_bytes = nonce + ciphertext + auth_tag
        res_str = b64encode(res_bytes).decode(cls.encoding_utf8)
        return res_str

    @classmethod
    def aes_gcm_decrypt(cls, encrypted_str, secret_key=None):
        '''
        使用AES-GCM算法解密
        '''
        res_bytes = b64decode(encrypted_str.encode(cls.encoding_utf8))
        nonce = res_bytes[:cls.IV_LEN]
        ciphertext = res_bytes[cls.IV_LEN:-cls.TAG_LEN]
        auth_tag = res_bytes[-cls.TAG_LEN:]
        secret_key = b64decode(secret_key or cls.KEY)
        aes_cipher = AES.new(secret_key, AES.MODE_GCM, nonce)
        return aes_cipher.decrypt_and_verify(ciphertext, auth_tag).decode(cls.encoding_utf8)

    @classmethod
    def aes_gcm_generate_secret(cls):
        '''
        生成256位长度的密钥，然后将密钥使用base64编码成字符串
        '''
        random_bytes = os.urandom(32)
        random_str = b64encode(random_bytes).decode(cls.encoding_utf8)
        return random_str


if __name__ == "__main__":

    begin_time = time.time()
    print("------------------------------------------------")

    # "passw0rd#!1": "btc0XTmmahvNU6xvFUJZl1PR3qf4jBJslljJNwEYlegYvWoBWi8D"
    # "Passw0rd": "jdlnFA4PvxOuKofuFVjOEFssBoCe6o101cB2RX6rIMKsU0nS"
    # "Teamsun@1": "vFzqdHmjjG9EUu8zibmsQocEezYniEI44lZoHmxi427jE9Fx5Q=="
    org_msg = "Python AES GCM NoPadding 加解密测试"
    print(f"原始信息: {org_msg}")

    # key = AESGCMCipher.aes_gcm_generate_secret()
    key = AESGCMCipher.KEY
    print(f"密码KEY: {key}")

    # en_msg = AESGCMCipher.aes_gcm_encrypt(org_msg, key)
    en_msg = AESGCMCipher.aes_gcm_encrypt(org_msg)
    print(f"加密信息: {en_msg}")

    # de_msg = AESGCMCipher.aes_gcm_decrypt(en_msg, key)
    de_msg = AESGCMCipher.aes_gcm_decrypt(en_msg)
    print(f"解密信息: {de_msg}")

    end_time = time.time()
    print("------------------------------------------------")
    print("耗时：%f 秒" % (end_time - begin_time))

    print("------------------------------------------------")
    begin_time = time.time()

    # key = "Q1ukKf5Oim3ZudDujNUbCQapp6lEjpm0CiCyVakg0TU="
    # # export PYREMOKIT_AES_GCM_KEY="Q1ukKf5Oim3ZudDujNUbCQapp6lEjpm0CiCyVakg0TU="
    os.environ['PYREMOKIT_AES_GCM_KEY'] = 'Q1ukKf5Oim3ZudDujNUbCQapp6lEjpm0CiCyVakg0TU='
    key = os.getenv("PYREMOKIT_AES_GCM_KEY")
    print(f"密码KEY: {key}")

    en_msg = "2vv4kQJVleIamW8Ba6GjwV4796VtPd5o540JYGnwgwlUQ8r6aQyc4X1aS8bAmaM40CT4C0sVUfxKUYd9EWleOyt21n74qzw26Wc3qMs="
    print(f"加密信息: {en_msg}")
    de_msg = AESGCMCipher.aes_gcm_decrypt(en_msg, key)
    print(f"解密信息: {de_msg}")

    end_time = time.time()
    print("------------------------------------------------")
    print("耗时：%f 秒" % (end_time - begin_time))

# vi:ts=4:sw=4:expandtab:ft=python:
