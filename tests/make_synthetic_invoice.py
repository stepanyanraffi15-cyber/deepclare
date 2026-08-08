"""Synthetic invoice, entirely fictitious, generated for a one-off end-to-end check.
Deliberately includes a freight line, which must NOT come back as goods."""
import pypdfium2 as pdfium  # noqa: F401  (ensures the engine is installed)
from PIL import Image, ImageDraw, ImageFont
import io

W,H=1240,1754  # A4 @ 150dpi
img=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(img)
def f(sz,b=False):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if b else
              "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        try: return ImageFont.truetype(p,sz)
        except Exception: pass
    return ImageFont.load_default()

d.text((60,50),"NORDVEK PLASTICS LLC",font=f(30,True),fill="black")
d.text((60,92),"Fabrikkveien 14, 7010 Trondheim, Norway",font=f(18),fill="black")
d.text((60,116),"Org. no. NO 981 234 567 MVA",font=f(18),fill="black")
d.text((60,175),"COMMERCIAL INVOICE",font=f(26,True),fill="black")
d.text((60,215),"Invoice No: NV-2026-0431",font=f(18),fill="black")
d.text((60,240),"Date: 14.07.2026",font=f(18),fill="black")
d.text((700,215),"Buyer:",font=f(18,True),fill="black")
d.text((700,240),"ARARAT IMPORT LLC",font=f(18),fill="black")
d.text((700,264),"12 Tigran Mets Ave, Yerevan, Armenia",font=f(16),fill="black")
d.text((700,288),"TIN: 01234567",font=f(16),fill="black")
d.text((60,320),"Terms: CIP YEREVAN            Currency: EUR",font=f(18),fill="black")

y=380
d.line((60,y-10,1180,y-10),fill="black",width=2)
for x,t in ((65,"No"),(120,"Description"),(560,"HS Code"),(690,"Qty"),(790,"Unit"),
            (880,"Pkgs"),(960,"Net kg"),(1070,"Amount")):
    d.text((x,y),t,font=f(17,True),fill="black")
d.line((60,y+26,1180,y+26),fill="black",width=2)

rows=[("1","Plastic storage box 40x60 cm, blue","3923101000","480","PCS","40","624.0","3 840.00"),
      ("2","Polyethylene bottle 1 L, natural","3923301000","1200","PCS","24","384.0","2 160.00"),
      ("3","PP woven sack 50 kg, printed","3923210000","5000","PCS","50","750.0","4 250.00"),
      ("4","Freight charge Trondheim - Yerevan","","1","LOT","","","1 450.00")]
y+=40
for r in rows:
    for x,t in zip((65,120,560,690,790,880,960,1070),r):
        d.text((x,y),t,font=f(16),fill="black")
    y+=34
d.line((60,y+4,1180,y+4),fill="black",width=1)
d.text((880,y+18),"TOTAL EUR",font=f(18,True),fill="black")
d.text((1070,y+18),"11 700.00",font=f(18,True),fill="black")
d.text((60,y+70),"Goods total (excl. freight): EUR 10 250.00",font=f(16),fill="black")
d.text((60,y+100),"Gross weight: 1 890 kg    Packages: 114 CARTONS",font=f(16),fill="black")
d.text((60,y+130),"Country of origin: NORWAY",font=f(16),fill="black")

img.save("/tmp/invoice_synthetic.pdf","PDF",resolution=150.0)
print("wrote /tmp/invoice_synthetic.pdf")
