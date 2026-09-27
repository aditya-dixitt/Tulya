# TULYA — 3-Minute Demo Video Script (Simple English)

**For the SIH26099 deck · Team AlgoRythms**
Screen recording of `reports/tulya_console.html`. Voice only, no webcam.

Narration is **400 words**. Read at a normal speaking speed and it comes to about
**2 minutes 55 seconds**. Every line is written the way you should say it, in full
sentences. Do not speed up to add more.

---

## Before you record

- [ ] Run `python3 tulya/build.py`, then open `reports/tulya_console.html` fresh
- [ ] Audit Log, then click **Reset demo state**, so the log is empty
- [ ] Test TULYA, then click **Reset the three cases**, so the answers are hidden
- [ ] Set the Performance slider to **0.92**
- [ ] Decide now which veto card you will open, and which pair you will approve
- [ ] Browser at 100% zoom, full screen, bookmarks bar hidden, all other tabs closed
- [ ] Record at 1920 by 1080, 30 frames per second
- [ ] Turn on cursor highlight if your recorder has it
- [ ] Record the voice separately from the screen. It is much easier to fix one sentence that way.

**Record the seven blocks below one by one.** Do not try to do it in a single take.
If you make a mistake, you only lose 25 seconds of work.

---

## BLOCK 1 · 0:00 to 0:23 · The problem

**On screen:** Console open on Control Tower. Keep the screen still for two seconds.
Then move the cursor slowly across the six company names in the header.

**Say:**

> "The same valve is kept in the stores of four different government oil companies.
> Each company has given it a different code. So nobody knows that it is the same
> item.
>
> This is TULYA. It reads the material list of every company, and it gives one single
> national code to each real item."

*(51 words. Stop for one full second after "the same item.")*

---

## BLOCK 2 · 0:23 to 0:39 · Where the numbers come from

**On screen:** Click the grey bar under the top menu so it opens. Leave it open.

**Say:**

> "One thing first. All the numbers you will see come from a test set that we locked
> before we tested on it. Some quantities in this demo are made up for the demo, and
> each one of them is marked on the screen."

*(45 words)*

Say this early, not at the end. If a judge finds an unmarked number later, they will
stop trusting the whole video.

---

## BLOCK 3 · 0:39 to 1:08 · Why duplicate codes happen

**On screen:** Test TULYA panel. Scroll so both item descriptions are fully visible.
Do not scroll while you speak. Click to show the answer only on the last line.

**Say:**

> "Look at these two items. The words are almost the same. The category is also the
> same. Only one specification is different.
>
> Now think of a store keeper. He sees cases like this many times a day, and he has
> no time to check. So he creates a new code. This is how duplicate codes are born.
> The fault is not his. The description itself is not clear.
>
> Here is the correct answer."

*(72 words. Stop for one and a half seconds before "Here is the correct answer", then click.)*

---

## BLOCK 4 · 1:08 to 1:42 · The part no other tool does

**On screen:** Hard-Key Vetoes panel. Open one card. Put the cursor on the reason
text inside the card while you explain it.

**Say:**

> "These pairs had the highest text similarity in the whole test. Our system rejected
> all of them.
>
> It rejected them because one specification was known on both sides, and the two
> values did not match. The system also tells you which specification it was.
>
> A normal text matching tool would accept these as correct matches. But looking
> similar is not the same as being the same item.
>
> There were 741 such difficult pairs. Our system rejected every single one."

*(83 words. Slow down on "But looking similar is not the same as being the same item." Stop for a beat before it and after it.)*

This block is the most important one in the video. If you re-record only one block
until it is clean, make it this one.

---

## BLOCK 5 · 1:42 to 2:04 · A person always decides

**On screen:** Review Queue. Move the cursor over the three numbers on one card as
you name them. Then go to Auto-Suggest and approve one pair on camera.

**Say:**

> "When the system is not sure, it does not decide. It sends the pair to a person.
> It also sorts these pairs by three things. How unsure it is. How little information
> was available. And how costly the item is.
>
> Even when the system is very sure, it still does not merge anything by itself."

*(59 words. Click Approve on the word "itself.")*

---

## BLOCK 6 · 2:04 to 2:24 · What the company gets

**On screen:** Golden Records, showing the group your approval just created. Then go
to Audit Log and point at the new entry at the top.

**Say:**

> "After approval, the item gets one national code. Every company still keeps its own
> old code. The national code only connects them. It does not remove them.
>
> The approval is also saved in a record that can never be changed. So any decision
> can be checked again later."

*(51 words)*

The line about old codes being kept is why a company can start using this without
changing its existing system. Do not cut it.

---

## BLOCK 7 · 2:24 to 2:55 · The results

**On screen:** Performance panel. Move the threshold slider slowly left and right
once, then bring it back to 0.92. On the last two lines, scroll down to the table of
test runs.

**Say:**

> "Now the results. Out of every hundred matches that the system suggests on its own,
> about ninety five are correct. And about fifty nine out of every hundred records
> still need a person to check them. We are showing the second number also, because
> that is the number usually hidden.
>
> This table shows every test we have run, including one test that gave a result
> below our own target. We have kept it here.
>
> One command creates every number in this video again.
>
> TULYA. One nation, one material code."

*(89 words. Say the two numbers slowly. Stop for a beat before "including one test that gave a result below our own target.")*

Ending on the test that failed is on purpose. It is the most believable thing in the
video, and almost no other team will show it.

---

## Text to show on screen

Judges often watch a small video without sound the first time. Put one short line at
the bottom left of each block and leave it there for the whole block. Keep it small
and do not animate it.

| Block | Text |
|---|---|
| 1 | Four companies. Four codes. One item. |
| 2 | Locked test set. Made-up quantities are marked. |
| 3 | Only one specification is different |
| 4 | 741 difficult pairs. All 741 rejected. |
| 5 | Nothing is merged without a person |
| 6 | Old codes are kept, not removed |
| 7 | 95 out of 100 suggestions correct. 59 out of 100 records need a person. |

---

## If you need to make it 2 minutes

Remove Block 5 completely, and keep only the first two sentences of Block 6. Keep
Blocks 1, 2, 3, 4 and 7 as they are. Never remove Block 2, because that is your
honesty, and never remove Block 4, because that is your new idea.

---

## Two things you must not say

1. **Do not say these numbers are from Sentence-BERT or MiniLM.** They come from the
   simpler TF-IDF encoder, because the build machine could not download the model.
   It is fine if the video does not mention the encoder at all. Just never say MiniLM.
2. **Do not read a made-up quantity as a result.** Stock, demand and purchase values
   in this demo are made up. This 3-minute video leaves out the Simulator and
   Procurement pages for that reason, so every number you say out loud is a real
   measured one.

---

## For a longer video later

The 7-minute live walkthrough is in `docs/TULYA-demo-script.md`. It covers the other
pages, such as Impact Simulator, Procurement Intelligence, Standards Knowledge Graph,
Collaboration and Material Passport, and it also has answers ready for the common
judge questions.
