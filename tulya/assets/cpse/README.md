# CPSE logo assets

The console renders a CPSE mark from whatever file is present here. Nothing in
this repository draws, approximates, recolours or redistributes a CPSE
trademark: a CPSE with no file here gets a neutral monogram container of the
same size, which is a placeholder, not a stand-in mark.

## What to add

One file per CPSE, named by its code in lower case:

    bpcl.svg    hpcl.svg    ongc.svg    iocl.svg    gail.svg    cpcl.svg

`.svg` is preferred; `.png`, `.jpg` and `.webp` also work, up to 512 KB each.
Prefer a file with a transparent background and some padding around the mark.

## Where each one comes from

| Code | Company                                      | Source to take the file from |
|------|----------------------------------------------|------------------------------|
| BPCL | Bharat Petroleum Corporation Limited          | bharatpetroleum.in — About BPCL › Media Kit › Image Library › Brand and Identity |
| HPCL | Hindustan Petroleum Corporation Limited       | hindustanpetroleum.com — media / brand pages |
| ONGC | Oil and Natural Gas Corporation Limited       | uxdt.nic.in logo repository (Government of India) |
| IOCL | Indian Oil Corporation Limited                | iocl.com — media / brand pages |
| GAIL | GAIL (India) Limited                          | gailonline.com — media / brand pages |
| CPCL | Chennai Petroleum Corporation Limited         | cpcl.co.in — media pages |

Prefer each company's own site or an official government repository over a
third-party logo aggregator: aggregator copies are often outdated, redrawn or
recoloured, and their licence terms do not come from the trademark owner.
Observe each owner's usage terms — these marks are used here to identify the
organisation, not to endorse or brand anything.

## After adding files

    python3 tulya/build.py

The build inlines each file it finds as a data URI and prints which codes are
still missing. No code change is needed: the marks appear at once in the
Cross-CPSE Material Network, Material Recommendation, Cross-CPSE Opportunities,
Procurement Intelligence, Material Passport, CPSE Analytics, the activity feed
and the search results. Aspect ratio is preserved everywhere
(`preserveAspectRatio="xMidYMid meet"` in SVG, `object-fit:contain` in HTML);
nothing is cropped, stretched, recoloured or filtered.
