# JC Video Factory Privacy Policy

Last updated: June 5, 2026

JC Video Factory is a local personal tool. It uses TikTok OAuth only so the authorized user can publish finished videos to their own TikTok account.

## Information Used

The tool may store the following data locally on the user's machine:

- TikTok OAuth access and refresh tokens in `storage/tiktok_token.json`.
- Temporary OAuth state values in `storage/tiktok_oauth_state.json`.
- Generated videos, captions, scripts, and task metadata under `storage/tasks/`.
- Draft story text in the browser's local storage.

The tool may request TikTok creator information, such as nickname, privacy options, interaction settings, and maximum allowed video duration, so the publishing screen can show the correct options.

## How Information Is Used

Data is used only to generate videos, show TikTok publishing options, upload the selected finished MP4, and check publish status. The tool does not sell personal information or share TikTok tokens with third parties.

## Data Control

The user controls the local files created by the tool. To disconnect TikTok, delete `storage/tiktok_token.json` and revoke the app from the TikTok account settings. Generated videos and task metadata can be deleted from `storage/tasks/`.

## Contact

For questions about this local tool, contact the owner of the repository or app deployment where this page is published.
