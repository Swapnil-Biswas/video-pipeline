# Prompt library

Every prompt below is preserved exactly as given (verbatim from the session transcript; only Markdown quoting added). Machine-readable copy: `docs/_extract/user_prompts.json`.

## A. User prompts (chronological, verbatim)

### P01 · 2026-10-29T17:02:32

- **Purpose:** Toolchain setup
- **Used in:** Session start
- **Input required:** GitHub URL
- **Output produced:** HyperFrames + FFmpeg installed
- **Reusable:** Yes: setup step

```text
https://github.com/heygen-com/hyperframes
setup hyperframes so we can use to edit videos
```

### P02 · 2026-10-29T18:00:49

- **Purpose:** Master brief: style transfer from reference videos to original brand content
- **Used in:** Film 1 (video/)
- **Input required:** 2 YouTube URLs, brand frontend path
- **Output produced:** 76 s launch film
- **Reusable:** Yes: the core 'style transfer' brief; swap URLs, brand path and product

```text
Take these two videos. : https://youtu.be/47FMSVb4f9E and https://youtu.be/oxcttz8jpO4. And the code, it's editing style: cuts, motion graphics, sound effects transitions and also music 
now use what you learned to edit my video in the same style as this with the same energy 
keep my content original and make the sound editing feel original and almost the same as the video. It should be equally engaging to make it professional.

The idea for this video is the HireCrew that we are building and another chat in the same Claude account. You may look at the frontend files that I made at  C:\Users\swapn\OneDrive\Desktop\HireCrew B&W\frontend and it should be in the exact theme. I hope you have a full idea of what HireCrew is. If not, kindly ask me. I'll provide you the PRD once again. You can proceed.
```

### P03 · 2026-10-29T18:25:10

- **Purpose:** Resume
- **Used in:** Several
- **Input required:** —
- **Output produced:** —
- **Reusable:** —

```text
continue
```

### P04 · 2026-10-29T18:29:29

- **Purpose:** Hardware directive
- **Used in:** Film 1
- **Input required:** —
- **Output produced:** GPU used for MusicGen/render
- **Reusable:** Yes

```text
use the gpu, laptop is now on charger
```

### P05 · 2026-10-29T18:32:43

- **Purpose:** Quality bar
- **Used in:** Film 1
- **Input required:** —
- **Output produced:** Extra review passes
- **Reusable:** Yes

```text
take ur time but make it studio quality
```

### P06 · 2026-10-29T18:47:20

- **Purpose:** Status check
- **Used in:** —
- **Input required:** —
- **Output produced:** —
- **Reusable:** —

```text
is it done?
```

### P07 · 2026-10-29T19:56:20

- **Purpose:** Revision brief: captions, human female voice, 5-second hook
- **Used in:** Film 1 v2
- **Input required:** Existing film
- **Output produced:** HeyGen voice, small captions, new hook
- **Reusable:** Yes: generic revision template

```text
Everything is very good. I want a few changes in the video. I want really small subtitles to be generated at the bottom of the video, and the voice needs to be female human not some robotic voice. Also the the script needs to be in such a way that the first 5 seconds of the video are eye-catching, and the viewer stops scrolling and looks at the video.
```

### P08 · 2026-10-29T20:14:07

- **Purpose:** Correction: dGPU not iGPU
- **Used in:** Film 1 v2
- **Input required:** —
- **Output produced:** Registry GPU preference + --gpu
- **Reusable:** Yes (Windows hybrid-GPU laptops)

```text
use nvidia gpu for rendering no ..... why use igpu?
```

### P09 · 2026-10-29T20:17:06

- **Purpose:** Voice selection after audition
- **Used in:** Film 1 v2
- **Input required:** Audition clips
- **Output produced:** Voice locked
- **Reusable:** Pattern: audition then pick

```text
Keep Joelle
```

### P10 · 2026-10-29T20:25:45

- **Purpose:** Re-format to 9:16 for website
- **Used in:** video-portrait/
- **Input required:** Landscape film
- **Output produced:** Portrait film
- **Reusable:** Yes: aspect re-layout

```text
now i want the same video but in portrait mode to be displayed on the website for phones. please modify the video accordingly
```

### P11 · 2026-10-29T20:41:43

- **Purpose:** Delivery request
- **Used in:** —
- **Input required:** —
- **Output produced:** File path
- **Reusable:** —

```text
give me the link to the portrait viedo
```

### P12 · 2026-10-29T20:56:47

- **Purpose:** Cut-down for Instagram
- **Used in:** video-reel/
- **Input required:** Long film
- **Output produced:** 15 s reel
- **Reusable:** Yes: duration re-edit

```text
now make a 15 sec video to be uploaded on insta that covers everything in a similar tone .. just reframe the entire thing and see that it covers everything
```

### P13 · 2026-10-29T21:12:37

- **Purpose:** Localisation: Hindi VO, English subs
- **Used in:** video-reel-hi/
- **Input required:** English reel
- **Output produced:** Hindi reel
- **Reusable:** Yes: language swap

```text
make the same video this time with hindi voiceover but with english subtitles
```

### P14 · 2026-10-29T21:23:03

- **Purpose:** Hook/punchline rewrite for reach
- **Used in:** video-reel-hi/
- **Input required:** Reel
- **Output produced:** New punchline
- **Reusable:** Yes

```text
keep the reel at 17 sec but use a different punchline to gain many audience so people think that they should really be investing or using our product
```

### P15 · 2026-10-29T21:25:51

- **Purpose:** Audience-specific hook (vibe coders)
- **Used in:** video-reel-hi/
- **Input required:** Reel
- **Output produced:** New opening
- **Reusable:** Yes

```text
hindi only .. make it different than the english one .... different starting
```

### P16 · 2026-10-29T21:25:57

- **Purpose:** (see text)
- **Used in:** 
- **Input required:** 
- **Output produced:** 
- **Reusable:** 

```text
[Request interrupted by user]
```

### P17 · 2026-10-29T21:26:21

- **Purpose:** Audience-specific hook (vibe coders)
- **Used in:** video-reel-hi/
- **Input required:** Reel
- **Output produced:** New opening
- **Reusable:** Yes

```text
hindi only .. make it different than the english one .... different starting ....some thing that every vibe coder relate.... waste of token wait for long time etc etc
```

### P18 · 2026-10-30T00:59:21

- **Purpose:** New brief: creator partner pitch
- **Used in:** video-sponsor/
- **Input required:** Offer terms
- **Output produced:** Pitch video
- **Reusable:** Yes: offer-explainer brief

```text
make an advertisement for the sponsors in which we specify the benefits we are giving them .. it shud be convincing enough to make them agree to making the promotional video .. heres is the idea: Unique referral code so that’s if its us used as coupons it will give tgem 10% commissions of order value life time and users will get 60% off for limited time
```

### P19 · 2026-10-30T01:23:20

- **Purpose:** QA feedback: misaligned graphics, plural audience
- **Used in:** video-sponsor/
- **Input required:** Render
- **Output produced:** Fixes
- **Reusable:** Yes: QA feedback pattern

```text
its bit out of place on some motion graphic shots ... another thing is that we are not targetting a single creator, we are targetting many togther .. so make the video accordinglyy
```

### P20 · 2026-10-30T01:33:49

- **Purpose:** (see text)
- **Used in:** 
- **Input required:** 
- **Output produced:** 
- **Reusable:** 

```text
[Request interrupted by user for tool use]
```

### P21 · 2026-10-30T02:12:30

- **Purpose:** Copywriting: Instagram caption
- **Used in:** Text
- **Input required:** Reel
- **Output produced:** Caption
- **Reusable:** Yes

```text
we are uploading the 15 sec english reel to insta ..... give the caption for the video
```

### P22 · 2026-10-30T02:13:09

- **Purpose:** Style constraint
- **Used in:** Captions
- **Input required:** —
- **Output produced:** —
- **Reusable:** Yes: house style

```text
dont put emojis please
```

### P23 · 2026-10-31T00:18:39

- **Purpose:** Copywriting: X post
- **Used in:** Text
- **Input required:** Film
- **Output produced:** Post text
- **Reusable:** Yes

```text
give me X description to post it .. the voiceover one video of 1:15
```

### P24 · 2026-11-04T08:54:28

- **Purpose:** Master brief for the FINAL video: style transfer from the Instagram reel
- **Used in:** video-showreel/ v1
- **Input required:** Reel URL
- **Output produced:** 28 s showreel
- **Reusable:** Yes: primary reusable brief

```text
Take this video : https://www.instagram.com/reel/Dd7LoTKSsbT/?xtok=Njg3N2h3MTEyNXFw. And the code, it's editing style: cuts, motion graphics, sound effects transitions and also music 
now use what you learned to edit my video in the same style as this with the same energy 
keep my content original and make the sound editing feel original and almost the same as the video. It should be equally engaging to make it professional. u can change the script if u want .. but the whole thign should revolve around HireCrew ..... take as much time as u need and use any resource u want including my gpu to render but make it studio grade.
```

### P25 · 2026-11-04T09:04:03

- **Purpose:** Confirms user fixed NVM trust
- **Used in:** —
- **Input required:** —
- **Output produced:** —
- **Reusable:** —

```text
done
```

### P26 · 2026-11-04T09:08:55

- **Purpose:** Ops instruction
- **Used in:** Environment repair
- **Input required:** —
- **Output produced:** Node reinstalled
- **Reusable:** —

```text
stop all the active npm proeccesses first thn reinstall
```

### P27 · 2026-11-04T11:29:21

- **Purpose:** QA feedback (screenshot of logo tile)
- **Used in:** video-showreel/ v1
- **Input required:** Screenshot
- **Output produced:** Logo centred
- **Reusable:** Yes

```text
alignment out of place
```

### P28 · 2026-11-05T09:43:06

- **Purpose:** QA + style-fidelity brief
- **Used in:** video-showreel/ v2 (final)
- **Input required:** Render + reference
- **Output produced:** Final render
- **Reusable:** Yes: final-polish brief

```text
There are multiple glitches in the video style. Try to fix them out. Take your time, render properly. Use the GPU and do it. It should be studio grade, and no glitches should exist in the video. Also, try to closely copy the editing style of the video. The Instagram reel is sent you earlier. Make sure to render the entire thing properly. Do not be in a hurry while doing this. Making certain glitches while making the video: either the font is out of place, or it's not properly aligned, or something. Please be careful with that respect .  it should be production level. Now make the video using the setup. You might recollect the older chats if you want to check what tools you used.
```

## B. MusicGen prompts (verbatim from the scripts)

Settings for all: `do_sample=True, guidance_scale=3.5, max_new_tokens=1500` (~30 s at 32 kHz), fp16 on CUDA, peak-normalised to 0.89.

| ID | Model | Used for | Prompt |
|---|---|---|---|
| P-M1 | facebook/musicgen-medium (gen.py, 90 s via 10 s continuation, seed 7) | Film 1 track A | "energetic modern tech product launch music, driving four-on-the-floor electronic beat, punchy kick drum, tight claps, deep sub bass, bright plucky synth arpeggios, clean and confident, uplifting, polished commercial production, 120 bpm, instrumental" |
| P-M2 | facebook/musicgen-medium (env MG_PROMPT, seed 23) | Film 1 track C | "modern minimal tech house for a sleek software product launch, punchy kick on every beat, crisp hi-hats, rolling sub bass, glassy synth stabs and bright pluck melody, confident and optimistic, clean high-end mix, 120 bpm, instrumental" |
| P-M3 | facebook/musicgen-stereo-medium (batch_reel2.py, seeds 101/303/505 → _p0) | **Showreel** takes | "upbeat modern motion graphics showreel music, bright plucky synths, punchy claps and snaps, crisp hi-hats, tight kick, energetic and playful, clean commercial mix, 124 bpm, instrumental" |
| P-M4 | facebook/musicgen-stereo-medium (seeds 202/404/606 → _p1) | **Showreel** takes — **404_p1 used in final** | "energetic tech promo track for a fast-cut motion design reel, glossy synth chords, bouncy bass, sharp percussion, confident and fun, polished modern production, 124 bpm, instrumental" |
| P-M5/6 | batch.py (`prompts_old`) | Film 1 batch takes | "energetic modern tech product launch music, driving four-on-the-floor electronic beat, punchy kick drum, tight claps, deep bass, bright plucky synth arpeggios, clean confident uplifting, polished commercial production, 120 bpm, instrumental" / "modern minimal tech house for a sleek software launch film, punchy kick on every beat, crisp hi-hats, rolling bassline, glassy synth stabs, bright pluck melody, confident optimistic, clean wide high-end mix, 120 bpm, instrumental" |

Reusable: yes — change genre words and the BPM token; keep `instrumental`. Pick BPM near the reference tempo found by `analyze`.

## C. Voice-over texts (HeyGen TTS; earlier films, not the showreel)

**video/assets/voice/lines.json** (film 1, per-slot lines):

- `hook` [0–6 s]: Your AI agent says it's done. It isn't. And you already paid for it.
- `oldway` [6–12 s]: Paid per month. Paid per chat. Your keys in a prompt. And zero proof it got done.
- `reveal` [12–18 s]: This is HireCrew. Hire a crew, not just an agent. Pay only for finished work.
- `order` [18–24 s]: Order any job in plain language, by text or by voice.
- `hold` [24–30 s]: Your payment is held. The seller gets paid only when you accept.
- `run` [30–36 s]: The agent works in your real apps, and every tool call is checked by code.
- `check` [36–42 s]: Then you check the result, right in your own apps. Not when the agent says so.
- `settle` [42–48 s]: Happy? Accept to pay. If not, dispute it and get a refund.
- `crew` [48–56 s]: Need more? A coordinator hires a whole crew of specialists, under a hard budget cap, and shows you every dollar.
- `bench` [56–62 s]: And every agent is tested on real jobs. Never on its own word.
- `recap` [62–68 s]: Payment held. Real apps. Code decides.
- `endcard` [68–76 s]: HireCrew. Pay only for finished work. Join today.

- **video-reel/assets/voice/crew.words.json**: Or hire a whole crew, under a hard cap.
- **video-reel/assets/voice/end.words.json**: Pay only for finished work. HireCrew.
- **video-reel/assets/voice/hook.words.json**: Your AI agent says it's done. It isn't.
- **video-reel/assets/voice/loop.words.json**: Order in plain words. Payment's held. Code checks every step. You verify it, then pay.
- **video-reel/assets/voice/reveal.words.json**: Meet HireCrew.
- **video-reel-hi/assets/voice/hi/crew.words.json**: या पूरी crew हायर कीजिए, तय बजट के अंदर।
- **video-reel-hi/assets/voice/hi/end.words.json**: पैसे सिर्फ़ पूरे हुए काम के।
- **video-reel-hi/assets/voice/hi/hook.words.json**: आपका AI एजेंट कहता है, काम हो गया। पर हुआ नहीं।
- **video-reel-hi/assets/voice/hi/loop.words.json**: आसान भाषा में ऑर्डर कीजिए। पेमेंट होल्ड रहता है। हर स्टेप कोड चेक करता है। आप वेरिफ़ाई करें, फिर पे करें।
- **video-reel-hi/assets/voice/hi/reveal.words.json**: मिलिए HireCrew से।

Audition line (English): "Your AI agent says it's done. It isn't. And you already paid for it." — Hindi audition: "आपका AI एजेंट कहता है, काम हो गया। पर हुआ नहीं।"

## D. Derived reusable prompts (written for the pipeline, not from the original chat)

These are new, marked as such, and live in `config/prompts.yaml`:

- `style_notes` — asks a vision-capable assistant to describe a reference's editing grammar from the contact sheets produced by `analyze`.
- `storyboard` — turns a product brief + style notes into a `project.yaml` scene list.
- `qa_review` — asks for a glitch list (clipped/overlapping text, misalignment, empty frames, font fallback) from preview sheets.