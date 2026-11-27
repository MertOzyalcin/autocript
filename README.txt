================================================================
  VIDEO TRANSCRIPT TOOL — README (USER GUIDE)
================================================================

WHAT DOES THIS APP DO?
----------------------
It turns speech in short videos (up to 3 minutes) into a
sentence-by-sentence transcript with timestamps.
- Upload a video or audio file from your computer, OR
- Paste a YouTube Shorts or Instagram Reel link.
- Everything runs locally on your own computer; nothing is
  installed system-wide.


WHAT YOU NEED BEFORE STARTING
-----------------------------
- Windows 10 or Windows 11.
- An internet connection for the first launch.
- About 400 MB of free disk space.
- An ElevenLabs account (a free account works) to turn speech
  into text.


SETUP IN 3 SIMPLE STEPS
-----------------------
1. EXTRACT THE ZIP FILE FIRST
   - Do not run the app from inside the zip file.
   - Right-click the zip file and choose "Properties". If you see
     an "Unblock" checkbox at the bottom, check it and click OK.
   - Right-click the zip file and choose "Extract All...".
   - Extract it to a simple folder such as "C:\video-transkript".
     (Avoid Desktop or Documents if they sync to OneDrive, so
     your keys and app files stay local.)

2. LAUNCH THE APP
   - Open the extracted "video-transkript" folder and double-click
     "baslat.cmd".
   - The first launch takes a few minutes while required
     components download automatically into this folder only.
     Nothing is installed anywhere else on your PC.
   - Keep the black window open while using the app. Close it when
     you are done.

3. ADD YOUR ELEVENLABS KEY
   - On first launch, your browser opens the Setup page in
     Turkish. Click "English" at the top right to switch the page
     to English. The app remembers your choice.
   - Click "Where do I get it?" on the page to follow the quick
     steps and paste your ElevenLabs key into the box.
   - Click "Test" first, then "Save".
   - A Groq key is optional; if added, it is used automatically as
     a backup whenever ElevenLabs is unavailable.
   - You only need to save your key once. Next time, the main page
     opens right away.


HOW TO USE
----------
1. Choose one option on the main screen:
   - Paste a YouTube Shorts or Instagram Reel link, OR
   - Drag and drop (or click to pick) a video/audio file from your
     computer.
   Note: Pasting a link clears any selected file, and picking a
   file clears any pasted link. For a YouTube link, only the
   audio is downloaded.

2. Click "Transcribe" and wait for the steps to finish.
   - If you submit several links from the same site in a row, the
     app puts them in a queue and waits at least 15 seconds
     between downloads ("Waiting in the YouTube queue" or
     "Waiting in the Instagram queue"). Each site has its own
     queue: a YouTube link never waits for Instagram.

3. Review and download your result:
   - Read the timestamped transcript on screen.
   - Dotted-underlined words had lower audio clarity; hover over
     them to see the confidence level.
   - Copy the text or download it as TXT, SRT (subtitles), or JSON.
   - A long Instagram caption shows its first 3 lines; click
     "Show more" to read the rest.

4. Interface language:
   - The "English" / "Türkçe" button at the top right switches
     the interface. Your choice is remembered.
   - The button is disabled while a job is running.
   - The black console window follows your Windows display
     language: Turkish on Turkish Windows, English otherwise.


GOOD TO KNOW
------------
- Videos up to 3 minutes are supported.
- Known limitation: Smart App Control blocks unsigned tools
  (Python, ffmpeg and others), so the app does not run on a
  computer where it is on. "baslat.cmd" says so and closes when it
  is on, and warns and continues when it is in evaluation mode.
  If you wish, you can turn it off under Windows Security → App &
  browser control → Smart App Control; the choice is yours.
- YouTube or Instagram may block some videos (private accounts,
  login prompts, multi-item carousels, or photos). When that
  happens, the app explains why and lets you click "Upload a
  file" to upload the video file directly.
- YouTube and Instagram links do not use an official method and
  may conflict with the sites' terms of use. No account or
  password is used. Use it only for content you have the right
  to transcribe.
- If you see made-up text over music or silence: the non-speech
  detector is off by default. To turn it on, add the line
  NONSPEECH_DETECTOR=silero to the ".env" file in this folder,
  close the black window and open "baslat.cmd" again. Extra
  packages download on that first launch.


PRIVACY
-------
- Your keys are stored only inside this folder and are never
  shared elsewhere.
- Only the audio is sent to your chosen transcription service
  (ElevenLabs, or Groq as backup).
- Uploaded and downloaded videos are deleted automatically as soon
  as the job finishes.
- No YouTube or Instagram account, password, or browser cookies
  are used.


QUICK TROUBLESHOOTING
---------------------
- First launch feels slow:
  Normal — components download only once. Later launches open in
  seconds.

- "No session. Open the app with baslat.cmd." warning:
  Double-click "baslat.cmd" instead of typing the address directly
  into your browser.

- Double-clicking "baslat.cmd" while already open:
  It simply brings up the already running app in your browser.

- "The video download tool isn't installed" or "The YouTube
  download tool is missing or out of date":
  Check your internet connection, close the black window and
  double-click "baslat.cmd" again. If it continues, upload the
  video as a file.

- Antivirus warning:
  Add this folder to your antivirus allowlist if it flags a
  downloaded component.

- Updating to a newer version:
  Extract the new zip into a fresh folder. Copy the ".env" file
  from your old folder into the new one to keep your saved keys.
