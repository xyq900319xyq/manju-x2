# waoowaoo API Key 解密

waoowaoo 将用户的 API Key 用 AES-256-GCM 加密存储在 `user_preferences.customProviders` (JSON 中的 `apiKey` 字段)。

## 参数

| 参数 | 值 |
|------|-----|
| 算法 | AES-256-GCM |
| IV 长度 | 16 bytes |
| 密钥派生 | PBKDF2-SHA256 |
| Salt | `waoowaoo-api-key-salt-v1` |
| 迭代 | 100,000 |
| 密钥长度 | 32 bytes |
| 密钥来源 | `API_ENCRYPTION_KEY` 环境变量 |
| 默认密钥 | `waoowaoo-opensource-fixed-key-2026` |
| 密文格式 | `iv_hex:authTag_hex:ciphertext_hex` |

## Python 解密脚本

```python
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import json

# === 从数据库获取密文 ===
# docker exec waoowaoo-mysql mysql -uroot -pwaoowaoo123 -N -B waoowaoo \
#   -e "SELECT customProviders FROM user_preferences WHERE userId='<userId>';"

# providers JSON 中每个 provider 的 apiKey 字段就是密文
providers_json = '[{"id":"...","apiKey":"iv_hex:authTag_hex:ciphertext_hex"}]'
providers = json.loads(providers_json)

SECRET = "waoowaoo-opensource-fixed-key-2026"  # 或从 docker inspect 获取 API_ENCRYPTION_KEY
SALT = "waoowaoo-api-key-salt-v1"
ITERATIONS = 100000

# 派生密钥
key = hashlib.pbkdf2_hmac('sha256', SECRET.encode(), SALT.encode(), ITERATIONS, 32)

for provider in providers:
    encrypted = provider.get('apiKey', '')
    if not encrypted or ':' not in encrypted:
        continue
    parts = encrypted.split(':')
    iv = bytes.fromhex(parts[0])
    auth_tag = bytes.fromhex(parts[1])
    ciphertext = bytes.fromhex(parts[2])

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext + auth_tag, None)
    provider['_decryptedKey'] = plaintext.decode('utf-8')

print(json.dumps(providers, indent=2))
```

## 注意事项

- 需要安装 `cryptography` 包：`pip install cryptography`
- 密文是三段式 hex 编码，如果从数据库查询结果被截断，检查终端/命令长度限制
- 如果解密失败抛异常，检查 `API_ENCRYPTION_KEY` 的值是否正确（从 docker-compose.yml 或 `docker inspect` 获取）
