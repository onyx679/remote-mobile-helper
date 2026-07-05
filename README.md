# Android remote control over Wi-Fi

This folder contains helper scripts for the open-source project `scrcpy`.

## First-time setup

1. On the Android phone, enable Developer options.
2. Enable USB debugging.
3. Connect the phone to this PC with USB.
4. Accept the RSA/USB debugging prompt on the phone.
5. Run:

```powershell
.\check-devices.ps1
```

If the device shows as `unauthorized`, unlock the phone and accept the debugging prompt.

## Start remote control by USB

```powershell
.\start-usb.ps1
```

## Start remote control by Wi-Fi

For the first Wi-Fi connection, keep USB connected and run:

```powershell
.\start-wifi.ps1
```

After that, you can usually unplug USB. If you know the phone IP address:

```powershell
.\start-wifi.ps1 -Ip 192.168.1.23
```

The phone and PC must be on the same network, and the phone must already trust this PC for USB debugging.

## Start remote control by Wi-Fi without USB

This requires Android 11+ with Wireless debugging enabled.

On the phone:

1. Open Developer options.
2. Enable Wireless debugging.
3. Open Wireless debugging.
4. Choose Pair device with pairing code.
5. Note the pairing address and pairing code, for example `192.168.1.23:37123` and `123456`.
6. Go back to the Wireless debugging screen and note the main IP address and port, for example `192.168.1.23:42157`.

Then run:

```powershell
.\pair-and-start-wifi.ps1 -PairAddress 192.168.1.23:37123 -PairCode 123456 -ConnectAddress 192.168.1.23:42157
```

The pairing port and connection port are usually different.

## Sync new camera photos to this PC

Keep the Wi-Fi ADB connection active, then run:

```powershell
.\sync-camera-photos.ps1
```

By default, existing photos are skipped and only photos taken after the script starts are copied to `camera-inbox`.

To scan once and exit:

```powershell
.\sync-camera-photos.ps1 -Once
```

To ask whether each new photo should be queued for AI review:

```powershell
.\sync-camera-photos.ps1 -PromptForAi
```

Queued photos are copied to `ai-outbox`, but they are not sent anywhere automatically.

To copy each new photo directly to the Windows clipboard:

```powershell
.\sync-camera-photos.ps1 -CopyToClipboard
```

After a new photo is copied, paste it into another app with `Ctrl+V`.

If the phone is upside down, rotate the clipboard output:

```powershell
.\sync-camera-photos.ps1 -CopyToClipboard -RotateDegrees 180
```

The original synced photo stays in `camera-inbox`; the rotated copy is saved in `camera-rotated`.

To manually queue a photo later:

```powershell
.\queue-photo-for-ai.ps1 -PhotoPath .\camera-inbox\IMG_20260621_190000.jpg
```

To manually copy an existing photo to the clipboard:

```powershell
.\copy-photo-to-clipboard.ps1 -PhotoPath .\camera-inbox\IMG_20260621_190000.jpg
```

Manual copy with rotation:

```powershell
.\copy-photo-to-clipboard.ps1 -PhotoPath .\camera-inbox\IMG_20260621_190000.jpg -RotateDegrees 180
```

To open the local folders:

```powershell
.\open-photo-folders.ps1
```

## Fast English word judgment

For practice workflows where the word text is already known:

```powershell
.\judge-word.ps1 -Word example -CopyAnswer
```

This uses a local English frequency list, so it avoids AI latency.

To try reading the current Android screen through accessibility text and judge the largest candidate word:

```powershell
.\judge-current-screen-word.ps1 -CopyAnswer -ShowDebug
```

For the current phone-camera workflow, use the scrcpy video-frame OCR path below.

## Camera photo to YES/NO

Process one photo:

```powershell
.\answer-photo.ps1 -PhotoPath .\camera-inbox\IMG_20260621_194838.jpg -CopyAnswer
```

Watch new photos and answer automatically:

```powershell
.\watch-answer-from-photos.ps1 -CopyAnswer
```

Show a large always-on-top result window:

```powershell
.\show-answer-window.ps1
```

Outputs:

- `latest-result.json`
- `latest-answer.txt`
- `latest-crop.png`

Start the full live pipeline:

```powershell
.\start-live-answer.ps1
```

For command-line-only live output directly from the phone:

```powershell
.\watch-phone-answer.ps1 -CopyAnswer
```

Current fast scrcpy video-frame OCR version:

```powershell
.\watch-phone-answer-fast.ps1 -CopyAnswer
```

## Portable package and migrate to another PC

Use this script to export only the required runtime files (exclude historical photos/debug outputs):

```powershell
cd C:\Users\11137\Documents\远程控制手机
.\make-portable-package.ps1
```

This creates a timestamped zip under `portable-release\`.

On the new machine:

```powershell
cd "C:\path\to\project"
.\setup-new-pc.ps1
python -m pip install -r requirements.txt
.\check-devices.ps1
```

Or clone from GitHub:

```powershell
git clone https://github.com/onyx679/remote-mobile-helper.git
cd remote-mobile-helper
.\setup-new-pc.ps1
python -m pip install -r requirements.txt
```

Then bind to your new phone serial:

```powershell
.\start-scrcpy-small.ps1 -Serial <serial>
```

If your serial is unstable, pass `-Serial` each time for:

- `start-scrcpy-small.ps1`
- `watch-phone-answer-fast.ps1`
- `start-photo-clipboard.ps1`

Recommended daily run:

```powershell
.\start-scrcpy-small.ps1 -Serial <serial>
start-word-answer.cmd
start-photo-clipboard.cmd
```

Stop in reverse:

```powershell
stop-word-answer.cmd
stop-photo-clipboard.cmd
```
