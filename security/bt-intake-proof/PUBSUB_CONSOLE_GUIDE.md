# Optional: create the three authorized Pub/Sub resources in the console

Use this only if you do **not** want to give me a separate Cloud login.

Stay in project **bt-intake-proof**. If Google asks to link billing, stop and tell me.

## 1. Topic

https://console.cloud.google.com/cloudpubsub/topic/create?project=bt-intake-proof

- Topic ID: `bt-intake-proof-contactus`
- Leave other defaults
- Create

## 2. Publisher for Gmail

On that topic → **Permissions** / **Add principal**

- Principal: `gmail-api-push@system.gserviceaccount.com`
- Role: **Pub/Sub Publisher**
- Save

## 3. Subscription

https://console.cloud.google.com/cloudpubsub/subscription/create?project=bt-intake-proof

- Subscription ID: `bt-intake-proof-contactus-sub`
- Topic: `bt-intake-proof-contactus`
- Delivery type: **Pull**
- Create

Then tell me those three exist. I will register `users.watch` with the already-approved `contactus@` read-only token.
