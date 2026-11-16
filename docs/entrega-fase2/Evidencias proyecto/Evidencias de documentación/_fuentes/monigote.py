import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(0.6, 1.0), dpi=200)
ax.set_xlim(-1, 1); ax.set_ylim(0, 3.4); ax.axis("off")
ax.add_patch(plt.Circle((0, 2.9), 0.38, fill=False, lw=2, color="#1f2937"))
kw = dict(color="#1f2937", lw=2, solid_capstyle="round")
ax.plot([0, 0], [2.52, 1.3], **kw)
ax.plot([-0.75, 0.75], [2.1, 2.1], **kw)
ax.plot([0, -0.6], [1.3, 0.1], **kw)
ax.plot([0, 0.6], [1.3, 0.1], **kw)
fig.savefig("img/actor.png", transparent=True, bbox_inches="tight", pad_inches=0.02)
