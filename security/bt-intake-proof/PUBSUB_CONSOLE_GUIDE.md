# Create the three authorized Pub/Sub resources

Daniel chose the Cloud Console path. Create **only** these three things in project **bt-intake-proof**. If Google asks to link billing, stop and tell me.

The top bar must show **bt-intake-proof**:
https://console.cloud.google.com/?project=bt-intake-proof

If Pub/Sub API is not on yet:
https://console.cloud.google.com/apis/library/pubsub.googleapis.com?project=bt-intake-proof → **Enable**

## 1. Create the topic

https://console.cloud.google.com/cloudpubsub/topic/create?project=bt-intake-proof

- Topic ID: `bt-intake-proof-contactus`
- Leave encryption, schema, and other defaults
- **Create**

Confirm it appears here:
https://console.cloud.google.com/cloudpubsub/topic/list?project=bt-intake-proof

## 2. Allow Gmail to publish to that topic

Open the topic:
https://console.cloud.google.com/cloudpubsub/topic/detail/bt-intake-proof-contactus?project=bt-intake-proof

1. Open the **Permissions** tab (or **SHOW INFO PANEL** → **Permissions**)
2. **Add principal**
3. New principal: `gmail-api-push@system.gserviceaccount.com`
4. Role: **Pub/Sub Publisher**
5. Save. If Google warns about a Google-owned service account, that is expected — continue.

## 3. Create the pull subscription

https://console.cloud.google.com/cloudpubsub/subscription/create?project=bt-intake-proof

- Subscription ID: `bt-intake-proof-contactus-sub`
- Select a Cloud Pub/Sub topic: `bt-intake-proof-contactus`
- Delivery type: **Pull**
- Leave other defaults
- **Create**

Confirm it appears here:
https://console.cloud.google.com/cloudpubsub/subscription/list?project=bt-intake-proof

## Then reply

Tell me: topic, Gmail publisher permission, and subscription are created.

I will register `users.watch` with the existing `contactus@` read-only token and show project, mailbox, topic, subscription, history ID, and expiration.

Do not send `BT-INTAKE-PROOF-*` emails until I report watch **PASS**.
