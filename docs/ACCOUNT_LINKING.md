# Postal AutoClip account linking

Postal AutoClip keeps developer-app secrets and OAuth tokens on the local PC under `secrets/`. The launcher opens the local account manager at `http://127.0.0.1:8790`.

## TikTok

1. Create a TikTok Developer app and add **Login Kit** plus the **Content Posting API**.
2. Configure the app as a Desktop integration and register this redirect URI exactly:

   `http://127.0.0.1:8790/tiktok/callback`

3. Request/enable the scopes AutoClip uses:
   - `user.info.basic`
   - `video.list`
   - `video.publish`
4. In Postal AutoClip, open **Accounts**.
5. Paste the TikTok **Client Key** and **Client Secret** once and click **Save App Keys**.
6. Click **Connect TikTok** and approve the browser authorization page.

AutoClip uses TikTok's Desktop OAuth/PKCE flow. The user access token is short-lived, so AutoClip stores the refresh token locally and refreshes the access token automatically before expiry.

## Instagram

Postal AutoClip intentionally uses **Facebook Login for Business** for Instagram because the local resumable Reel-upload flow can upload the rendered MP4 directly from the PC. The newer direct Instagram Login path is simpler but does not provide the same local resumable upload path; it normally requires Meta to fetch media from a publicly reachable URL.

1. Use an Instagram **Professional** account (Creator or Business) linked to a Facebook Page.
2. Create a Meta app with the Instagram API / Facebook Login for Business configuration needed for content publishing.
3. Register this OAuth redirect URI exactly:

   `http://127.0.0.1:8790/instagram/callback`

4. Ensure the app can request the permissions used by AutoClip:
   - `pages_show_list`
   - `pages_read_engagement`
   - `instagram_basic`
   - `instagram_content_publish`
   - `instagram_manage_insights`
5. In Postal AutoClip, open **Accounts**.
6. Paste the Meta **App ID** and **App Secret** once and click **Save App Keys**.
7. Click **Connect Instagram** and approve the browser authorization page.

AutoClip exchanges the browser authorization code for a user token, retrieves the Pages you manage, discovers linked Professional Instagram accounts, and stores the correct Page access token + Instagram user ID locally. If more than one eligible Instagram account is found, the Accounts page lets you choose which one AutoClip should use.

## Local files

The account manager writes only local credential files:

- `secrets/tiktok_app.json`
- `secrets/tiktok_token.json`
- `secrets/instagram_app.json`
- `secrets/instagram_token.json`

The `secrets/` directory is Git-ignored and must never be committed.

## Local URLs

- Main AutoClip dashboard: `http://127.0.0.1:8787`
- Analytics: `http://127.0.0.1:8787/static/analytics.html`
- Accounts: `http://127.0.0.1:8790`

All three services bind to localhost only.
