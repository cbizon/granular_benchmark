import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Presentation, PresentationFile } from "@oai/artifact-tool";


const HERE = path.dirname(fileURLToPath(import.meta.url));
const STORY_ROOT = path.resolve(HERE, "../..");
const ASSETS = path.join(STORY_ROOT, "assets");
const RENDERED = path.join(STORY_ROOT, "rendered");
const OUTPUT = path.join(STORY_ROOT, "granular-benchmark-story.pptx");

const W = 1280;
const H = 720;
const C = {
  ink: "#111111",
  muted: "#52616B",
  line: "#B8BCC4",
  panel: "#EDEDED",
  paper: "#F8F8F6",
  blue: "#3D8DFF",
  cyan: "#6DCBF4",
  paleBlue: "#EAF5FB",
  deepBlue: "#12364A",
  orange: "#F57748",
  paleOrange: "#FCE8DE",
  green: "#2F9E72",
  paleGreen: "#E6F4ED",
  red: "#C94A42",
  paleRed: "#F7E5E3",
  white: "#FFFFFF",
};
const FONT = "Helvetica Neue";


async function readBlob(filePath) {
  const bytes = await fs.readFile(filePath);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}


function addShape(slide, geometry, position, fill = "none", line = null, name = undefined) {
  return slide.shapes.add({
    geometry,
    name,
    position,
    fill,
    line: line ?? { style: "solid", fill: "none", width: 0 },
  });
}


function addText(
  slide,
  text,
  position,
  {
    size = 28,
    color = C.ink,
    bold = false,
    align = "left",
    valign = "top",
    autoFit = "shrinkText",
    lineSpacing = 1.02,
    name = undefined,
    italic = false,
  } = {},
) {
  const shape = addShape(slide, "textbox", position, "none", null, name);
  shape.text = text;
  shape.text.style = {
    fontSize: size,
    typeface: FONT,
    color,
    bold,
    italic,
    alignment: align,
    verticalAlignment: valign,
    autoFit,
    wrap: "square",
    lineSpacing,
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}


function addRichText(slide, paragraphs, position, style = {}) {
  const shape = addShape(slide, "textbox", position, "none");
  shape.text = paragraphs;
  shape.text.style = {
    fontSize: style.size ?? 26,
    typeface: FONT,
    color: style.color ?? C.ink,
    alignment: style.align ?? "left",
    verticalAlignment: style.valign ?? "top",
    autoFit: style.autoFit ?? "shrinkText",
    wrap: "square",
    lineSpacing: style.lineSpacing ?? 1.05,
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}


function addLine(slide, x, y, width, height = 0, color = C.line, stroke = 2, dashed = false) {
  return addShape(
    slide,
    "straightConnector1",
    { left: x, top: y, width, height },
    "none",
    { style: dashed ? "dashed" : "solid", fill: color, width: stroke },
  );
}


function addArrow(slide, x, y, width, height, color = C.blue) {
  return addShape(
    slide,
    "rightArrow",
    { left: x, top: y, width, height },
    color,
    { style: "solid", fill: color, width: 1 },
  );
}


async function addImage(slide, filePath, position, { fit = "contain", geometry = "rect", alt = "" } = {}) {
  const ext = path.extname(filePath).toLowerCase();
  const contentType = ext === ".gif" ? "image/gif" : "image/png";
  return slide.images.add({
    blob: await readBlob(filePath),
    contentType,
    alt,
    fit,
    geometry,
    position,
  });
}


function addHeader(slide, title, number, kicker = "GRANULAR SIMULATION BENCHMARK", dark = false) {
  const ink = dark ? C.white : C.ink;
  const muted = dark ? "#B9C8D1" : C.muted;
  addText(slide, kicker, { left: 42, top: 30, width: 650, height: 22 }, {
    size: 14,
    color: muted,
    bold: true,
  });
  addText(slide, title, { left: 42, top: 58, width: 1160, height: 76 }, {
    size: 44,
    color: ink,
    bold: true,
  });
  addText(slide, String(number).padStart(2, "0"), { left: 1182, top: 650, width: 56, height: 22 }, {
    size: 15,
    color: muted,
    align: "right",
  });
}


function addSectionTag(slide, text, x, y, width, { fill = C.ink, color = C.white } = {}) {
  addShape(slide, "roundRect", { left: x, top: y, width, height: 34 }, fill, {
    style: "solid",
    fill,
    width: 1,
  });
  addText(slide, text, { left: x + 12, top: y + 7, width: width - 24, height: 20 }, {
    size: 14,
    color,
    bold: true,
  });
}


function setNotes(slide, presenterText, sources = []) {
  const sourceBlock = sources.length
    ? `\n\n[Sources]\n${sources.map((source) => `- ${source}`).join("\n")}\n[/Sources]`
    : "";
  slide.speakerNotes.textFrame.setText(`${presenterText}${sourceBlock}`);
  slide.speakerNotes.setVisible(true);
}


function addBulletList(slide, items, position, { size = 26, color = C.ink, gap = 18 } = {}) {
  const rowHeight = (position.height - gap * (items.length - 1)) / items.length;
  items.forEach((item, index) => {
    const y = position.top + index * (rowHeight + gap);
    addShape(slide, "ellipse", { left: position.left, top: y + 8, width: 12, height: 12 }, C.blue);
    addText(slide, item, {
      left: position.left + 26,
      top: y,
      width: position.width - 26,
      height: rowHeight,
    }, { size, color });
  });
}


function addParticle(slide, x, y, radius, fill = C.orange, line = C.ink) {
  return addShape(
    slide,
    "ellipse",
    { left: x - radius, top: y - radius, width: radius * 2, height: radius * 2 },
    fill,
    { style: "solid", fill: line, width: 1.5 },
  );
}


function addCollisionPair(slide, x, y, direction, fill = C.orange) {
  addParticle(slide, x, y, 30, fill);
  addParticle(slide, x + direction * 100, y, 30, fill);
  addArrow(
    slide,
    direction > 0 ? x + 36 : x - 94,
    y - 11,
    54,
    22,
    direction > 0 ? C.deepBlue : C.orange,
  );
}


async function buildDeck() {
  await fs.mkdir(RENDERED, { recursive: true });
  const deck = Presentation.create({ slideSize: { width: W, height: H } });

  // 1. Cover
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addShape(slide, "rect", { left: 0, top: 0, width: 18, height: H }, C.blue);
    addSectionTag(slide, "AI × PHYSICS", 52, 46, 122, { fill: C.deepBlue });
    addText(slide, "Can an AI agent\nrediscover a granular\nsimulation?", {
      left: 52, top: 132, width: 540, height: 250,
    }, { size: 64, bold: true, lineSpacing: 0.92 });
    addText(
      slide,
      "A controlled benchmark for algorithmic reconstruction, not image imitation.",
      { left: 55, top: 420, width: 490, height: 96 },
      { size: 26, color: C.muted, lineSpacing: 1.1 },
    );
    addShape(slide, "roundRect", { left: 628, top: 42, width: 610, height: 610 }, C.paleBlue, {
      style: "solid", fill: C.line, width: 1,
    });
    await addImage(
      slide,
      path.join(ASSETS, "reference-rendered", "updated-c-montage.png"),
      { left: 646, top: 60, width: 574, height: 574 },
      { fit: "contain", geometry: "roundRect", alt: "Reference C simulation patterns" },
    );
    addText(slide, "Chris Bizon · first draft", { left: 55, top: 642, width: 440, height: 24 }, {
      size: 16, color: C.muted,
    });
    setNotes(
      slide,
      "Open with the central question. This is not primarily a benchmark of whether a model can make a plausible picture. It is a benchmark of whether an agent can independently reconstruct the physical simulation that produced those pictures.",
      ["Local benchmark reference rendering: artifacts/reference/generated and harness/scripts/render_reference_snapshots.py"],
    );
  }

  // 2. The original impulse
  {
    const slide = deck.slides.add();
    slide.background.fill = C.ink;
    addText(slide, "I wanted to try Fable\non a biology problem.", {
      left: 72, top: 96, width: 760, height: 190,
    }, { size: 68, bold: true, color: C.white, lineSpacing: 0.94 });
    addText(slide, "That was the obvious experiment.", {
      left: 76, top: 325, width: 520, height: 52,
    }, { size: 28, color: "#B9C8D1" });
    addLine(slide, 76, 430, 520, 0, "#466579", 2);
    addText(slide, "It would not do the biology.", {
      left: 76, top: 464, width: 680, height: 88,
    }, { size: 44, bold: true, color: C.cyan });
    addText(slide, "02", { left: 1182, top: 650, width: 56, height: 22 }, {
      size: 15, color: "#B9C8D1", align: "right",
    });
    setNotes(
      slide,
      "This is the personal starting point: the original goal was simply to see how Fable behaved on a scientific problem. When biology was off the table, the question became what other experiment would still expose real scientific reasoning.",
    );
  }

  // 3. The pivot
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "That forced a better experiment.", 3, "THE PIVOT");
    addText(slide, "Choose a problem where both the result and the method are inspectable.", {
      left: 44, top: 145, width: 980, height: 52,
    }, { size: 30, color: C.muted });
    const cards = [
      ["01", "Known science", "A problem I understand well enough to recognize shortcuts and mistakes."],
      ["02", "Visible target", "A paper with unmistakable patterns that make qualitative failure obvious."],
      ["03", "Inspectable algorithm", "A correct implementation whose scheduling, collision law, and numerical pathologies can be audited."],
    ];
    cards.forEach(([number, title, body], index) => {
      const x = 42 + index * 407;
      addShape(slide, "roundRect", { left: x, top: 238, width: 374, height: 338 }, C.panel);
      addText(slide, number, { left: x + 28, top: 268, width: 70, height: 58 }, {
        size: 42, bold: true, color: C.blue,
      });
      addText(slide, title, { left: x + 28, top: 346, width: 310, height: 42 }, {
        size: 30, bold: true,
      });
      addText(slide, body, { left: x + 28, top: 410, width: 310, height: 122 }, {
        size: 22, color: C.muted, lineSpacing: 1.12,
      });
    });
    setNotes(
      slide,
      "The failure to start with biology was useful. It pushed the experiment toward a domain where a visually impressive answer could be separated from a physically and algorithmically correct answer.",
    );
  }

  // 4. The paper
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "The target was a 1998 granular-physics result.", 4, "THE PAPER");
    addShape(slide, "roundRect", { left: 54, top: 140, width: 470, height: 525 }, C.white, {
      style: "solid", fill: C.line, width: 1,
    });
    await addImage(
      slide,
      path.join(ASSETS, "bizon-paper-page-1.png"),
      { left: 74, top: 155, width: 430, height: 495 },
      { fit: "contain", alt: "First page of Bizon et al. 1998" },
    );
    addText(slide, "Patterns in 3D Vertically Oscillated Granular Layers", {
      left: 580, top: 170, width: 600, height: 120,
    }, { size: 43, bold: true, lineSpacing: 0.98 });
    addText(slide, "Simulation and experiment", {
      left: 584, top: 315, width: 520, height: 42,
    }, { size: 29, color: C.blue, bold: true });
    addText(slide, "Bizon et al. · Physical Review Letters · 1998", {
      left: 584, top: 382, width: 560, height: 36,
    }, { size: 22, color: C.muted });
    addLine(slide, 584, 454, 580, 0, C.line, 2);
    addText(slide, "A thin granular layer, shaken vertically, spontaneously forms squares, stripes, and hexagons.", {
      left: 584, top: 482, width: 572, height: 116,
    }, { size: 28, lineSpacing: 1.08 });
    setNotes(
      slide,
      "The challenge is anchored to a compact paper with a memorable Figure 1 and a very specific computational method. The images are accessible, but reproducing them honestly requires understanding the collision model and event scheduler.",
      ["challenge/sources/bizon1998a.pdf"],
    );
  }

  // 5. Physical setup
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "A thin layer of hard spheres sits in a vibrating box.", 5, "THE PHYSICS");
    addShape(slide, "roundRect", { left: 60, top: 145, width: 730, height: 480 }, C.paleBlue, {
      style: "solid", fill: C.line, width: 1.5,
    });
    addLine(slide, 135, 205, 0, 340, C.ink, 6);
    addLine(slide, 715, 205, 0, 340, C.ink, 6);
    addLine(slide, 135, 545, 580, 0, C.ink, 8);
    for (let row = 0; row < 7; row += 1) {
      for (let col = 0; col < 12; col += 1) {
        const jitter = ((row * 13 + col * 7) % 9) - 4;
        const x = 165 + col * 44 + (row % 2) * 18 + jitter;
        const y = 510 - row * 34 - ((row * 5 + col * 3) % 8);
        if (x < 690) addParticle(slide, x, y, 15, row > 4 ? "#F8B28E" : C.orange, "#8E4B31");
      }
    }
    addShape(slide, "upDownArrow", { left: 740, top: 410, width: 34, height: 135 }, C.blue);
    addText(slide, "sinusoidal\nvertical drive", { left: 645, top: 360, width: 126, height: 64 }, {
      size: 18, bold: true, color: C.blue, align: "right",
    });
    addShape(slide, "downArrow", { left: 95, top: 190, width: 30, height: 90 }, C.deepBlue);
    addText(slide, "gravity", { left: 68, top: 164, width: 94, height: 28 }, {
      size: 18, bold: true, color: C.deepBlue,
    });
    addText(slide, "stationary\nsidewalls", { left: 152, top: 230, width: 110, height: 62 }, {
      size: 18, bold: true,
    });
    addText(slide, "100 particle diameters", { left: 300, top: 568, width: 285, height: 28 }, {
      size: 19, color: C.muted, align: "center",
    });
    addText(slide, "The reference simulation", { left: 846, top: 166, width: 340, height: 42 }, {
      size: 30, bold: true,
    });
    addBulletList(slide, [
      "60,000 hard spheres",
      "Gravity between collisions",
      "Instantaneous binary impacts",
      "Moving bottom plate",
      "Hard, non-periodic sidewalls",
    ], { left: 850, top: 236, width: 330, height: 292 }, { size: 23, gap: 12 });
    addText(slide, "The forcing injects energy. Inelastic collisions remove it.", {
      left: 850, top: 568, width: 330, height: 58,
    }, { size: 22, color: C.blue, bold: true });
    setNotes(
      slide,
      "The setup is deliberately simple: hard spheres in a square container under gravity, with a vertically oscillating bottom and fixed sidewalls. Complexity emerges from repeated dissipative collisions.",
      ["challenge/sources/bizon1998a.pdf", "artifacts/reference/generated/manifest.json"],
    );
  }

  // 6. Elastic and inelastic
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "Elastic and inelastic collisions differ in what they preserve.", 6, "COLLISION PHYSICS");
    const columns = [
      {
        x: 48, fill: C.paleGreen, accent: C.green, title: "Elastic", e: "e = 1",
        body: "Relative normal speed is preserved. Kinetic energy is not lost in the impact.",
      },
      {
        x: 654, fill: C.paleOrange, accent: C.orange, title: "Inelastic", e: "0 < e < 1",
        body: "The particles separate more slowly than they approached. Mechanical energy becomes heat, deformation, and sound.",
      },
    ];
    columns.forEach((column, index) => {
      addShape(slide, "roundRect", { left: column.x, top: 150, width: 578, height: 470 }, column.fill);
      addText(slide, column.title, { left: column.x + 30, top: 178, width: 280, height: 50 }, {
        size: 38, bold: true,
      });
      addSectionTag(slide, column.e, column.x + 402, 184, 132, {
        fill: column.accent,
        color: C.white,
      });
      addText(slide, "before", { left: column.x + 46, top: 262, width: 100, height: 28 }, {
        size: 18, color: C.muted, bold: true,
      });
      addText(slide, "after", { left: column.x + 340, top: 262, width: 100, height: 28 }, {
        size: 18, color: C.muted, bold: true,
      });
      addCollisionPair(slide, column.x + 126, 350, 1, column.accent);
      addArrow(slide, column.x + 270, 337, 54, 26, C.muted);
      if (index === 0) {
        addCollisionPair(slide, column.x + 398, 350, -1, column.accent);
      } else {
        addParticle(slide, column.x + 380, 350, 30, column.accent);
        addParticle(slide, column.x + 480, 350, 30, column.accent);
        addArrow(slide, column.x + 416, 341, 27, 18, C.deepBlue);
        addShape(slide, "leftArrow", { left: column.x + 448, top: 341, width: 27, height: 18 }, C.orange);
      }
      addText(slide, column.body, { left: column.x + 32, top: 445, width: 510, height: 118 }, {
        size: 24, color: C.muted, lineSpacing: 1.1,
      });
    });
    setNotes(
      slide,
      "The coefficient of restitution e is the ratio of separation speed to approach speed along the collision normal. With e below one, every impact dissipates energy. That dissipation is what makes granular matter qualitatively different from an ideal gas of billiard balls.",
      ["challenge/sources/bizon1998a.pdf", "challenge/sources/walton-1993-chapter-25.pdf"],
    );
  }

  // 7. Patterns
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "The layer organizes into standing-wave patterns.", 7, "THE TARGET");
    const panels = [
      ["a", "squares · f/2"], ["b", "stripes · f/2"], ["c", "hexagons · phase 1"], ["d", "hexagons · phase 2"],
      ["e", "flat · f/2"], ["f", "squares · f/4"], ["g", "stripes · f/4"], ["h", "hexagons · f/4"],
    ];
    for (let i = 0; i < panels.length; i += 1) {
      const [id, label] = panels[i];
      const col = i % 4;
      const row = Math.floor(i / 4);
      const x = 42 + col * 305;
      const y = 146 + row * 246;
      addShape(slide, "roundRect", { left: x, top: y, width: 274, height: 218 }, C.white, {
        style: "solid", fill: C.line, width: 1,
      });
      await addImage(
        slide,
        path.join(ASSETS, "figure1-panels", `figure1-${id}.png`),
        { left: x + 10, top: y + 10, width: 254, height: 160 },
        { fit: "cover", alt: `Paper Figure 1 panel ${id}` },
      );
      addText(slide, `${id}   ${label}`, { left: x + 12, top: y + 181, width: 248, height: 24 }, {
        size: 17, bold: true,
      });
    }
    addText(slide, "The geometry changes with forcing frequency and acceleration; the pattern can also repeat every two or four drive cycles.", {
      left: 48, top: 647, width: 1100, height: 36,
    }, { size: 21, color: C.muted });
    setNotes(
      slide,
      "Figure 1 gives a compact visual target: squares, stripes, alternating hexagons, and a flat state across f/2 and f/4 responses. The benchmark uses all seven simulation cases behind these eight image panels.",
      ["challenge/sources/bizon1998a.pdf", "output/presentations/granular-benchmark-story/assets/figure1-manifest.json"],
    );
  }

  // 8. Animation
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    await addImage(
      slide,
      path.join(ASSETS, "reference-patterns.gif"),
      { left: 0, top: 0, width: W, height: H },
      { fit: "contain", alt: "Animated reference C surface-height patterns" },
    );
    addText(slide, "08", { left: 1182, top: 682, width: 56, height: 20 }, {
      size: 14, color: C.muted, align: "right",
    });
    setNotes(
      slide,
      "This animation is generated directly from the benchmark's stored trajectories from the updated C code. Every panel is sampled at the same forcing phase. In presentation mode the GIF should animate; the included sidecar GIF can also be used independently.",
      ["artifacts/reference/generated/*/trajectory.npz", "harness/balls_bench/metrics.py"],
    );
  }

  // 9. Timescale separation
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "Collisions are extremely brief compared with free flight.", 9, "WHY EVENT-DRIVEN?");
    addText(slide, "physical time", { left: 80, top: 190, width: 170, height: 28 }, {
      size: 19, color: C.muted, bold: true,
    });
    addLine(slide, 88, 370, 1090, 0, C.ink, 3);
    const events = [230, 480, 760, 1040];
    events.forEach((x, index) => {
      addLine(slide, x, 310, 0, 120, index === 2 ? C.orange : C.blue, 5);
      addParticle(slide, x - 26, 270, 17, index === 2 ? C.orange : C.blue, C.white);
      addParticle(slide, x + 26, 270, 17, index === 2 ? C.orange : C.blue, C.white);
      addText(slide, "collision", { left: x - 48, top: 445, width: 96, height: 24 }, {
        size: 17, color: C.muted, align: "center",
      });
    });
    [[230, 480], [480, 760], [760, 1040]].forEach(([start, end]) => {
      addText(slide, "ballistic motion under gravity", {
        left: start + 18, top: 335, width: end - start - 36, height: 28,
      }, { size: 18, color: C.deepBlue, align: "center", italic: true });
    });
    addShape(slide, "roundRect", { left: 130, top: 540, width: 1010, height: 88 }, C.paleBlue);
    addText(slide, "Do not march through every tiny time step. Jump directly from one collision event to the next.", {
      left: 166, top: 563, width: 940, height: 46,
    }, { size: 29, bold: true, align: "center" });
    setNotes(
      slide,
      "Hard-sphere impacts are modeled as instantaneous, while particles spend most of their time in analytically predictable free flight. An event-driven algorithm exploits that separation by jumping to the next collision rather than resolving empty time.",
      ["challenge/sources/bizon1998a.pdf", "challenge/sources/lubachevsky-1991-billiards.pdf"],
    );
  }

  // 10. Event loop
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "The simulation advances by processing a collision schedule.", 10, "EVENT-DRIVEN HARD SPHERES");
    const steps = [
      ["1", "Predict", "Find the next particle-particle, particle-wall, or particle-plate collision."],
      ["2", "Jump", "Advance the simulation clock directly to that event."],
      ["3", "Resolve", "Apply the collision law to velocity and spin."],
      ["4", "Reschedule", "Recompute only events invalidated by the collision."],
    ];
    steps.forEach(([number, title, body], index) => {
      const x = 42 + index * 306;
      const fill = index === 2 ? C.paleOrange : C.panel;
      addShape(slide, "roundRect", { left: x, top: 188, width: 270, height: 350 }, fill);
      addShape(slide, "ellipse", { left: x + 24, top: 216, width: 56, height: 56 }, index === 2 ? C.orange : C.blue);
      addText(slide, number, { left: x + 24, top: 229, width: 56, height: 32 }, {
        size: 24, color: C.white, bold: true, align: "center",
      });
      addText(slide, title, { left: x + 24, top: 300, width: 220, height: 42 }, {
        size: 31, bold: true,
      });
      addText(slide, body, { left: x + 24, top: 370, width: 220, height: 126 }, {
        size: 21, color: C.muted, lineSpacing: 1.12,
      });
      if (index < 3) addArrow(slide, x + 274, 333, 28, 25, C.deepBlue);
    });
    addText(slide, "Priority queue ordered by event time", {
      left: 440, top: 581, width: 400, height: 40,
    }, { size: 24, color: C.deepBlue, bold: true, align: "center" });
    setNotes(
      slide,
      "The core loop is a priority queue of predicted events. A correct implementation must preserve event ordering, invalidate stale predictions, handle the moving plate, and update translational and rotational velocities according to the collision model.",
      ["challenge/sources/bizon1998a.pdf", "challenge/sources/rapaport-1980-event-scheduling.html"],
    );
  }

  // 11. Delayed states and virtual cells
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "Two implementation ideas keep 60,000 particles tractable.", 11, "THE ORIGINAL ALGORITHM");
    addShape(slide, "roundRect", { left: 42, top: 154, width: 566, height: 470 }, C.panel);
    addText(slide, "Delayed states", { left: 72, top: 184, width: 290, height: 44 }, {
      size: 34, bold: true,
    });
    addText(slide, "Update a particle's position only when an event actually needs it.", {
      left: 72, top: 240, width: 480, height: 72,
    }, { size: 23, color: C.muted });
    for (let i = 0; i < 48; i += 1) {
      const col = i % 8;
      const row = Math.floor(i / 8);
      const active = i === 27 || i === 28;
      addParticle(
        slide,
        112 + col * 58,
        354 + row * 38,
        11,
        active ? C.orange : "#C7CDD1",
        active ? "#8E4B31" : C.white,
      );
    }
    addText(slide, "Only the colliding pair is brought to the current time.", {
      left: 88, top: 575, width: 474, height: 34,
    }, { size: 19, color: C.deepBlue, bold: true, align: "center" });

    addShape(slide, "roundRect", { left: 652, top: 154, width: 586, height: 470 }, C.paleBlue);
    addText(slide, "Virtual cells", { left: 682, top: 184, width: 290, height: 44 }, {
      size: 34, bold: true,
    });
    addText(slide, "Search nearby spatial cells instead of testing every possible particle pair.", {
      left: 682, top: 240, width: 490, height: 72,
    }, { size: 23, color: C.muted });
    const gridX = 740;
    const gridY = 336;
    const cell = 50;
    for (let row = 0; row < 5; row += 1) {
      for (let col = 0; col < 7; col += 1) {
        const near = row >= 1 && row <= 3 && col >= 2 && col <= 4;
        addShape(slide, "rect", {
          left: gridX + col * cell,
          top: gridY + row * cell,
          width: cell,
          height: cell,
        }, near ? "#CDEAF7" : C.white, { style: "solid", fill: C.line, width: 1 });
      }
    }
    addParticle(slide, gridX + 3.5 * cell, gridY + 2.5 * cell, 13, C.orange, "#8E4B31");
    addText(slide, "Candidate neighbors are local.", {
      left: 744, top: 598, width: 350, height: 28,
    }, { size: 19, color: C.deepBlue, bold: true, align: "center" });
    setNotes(
      slide,
      "Delayed states avoid globally advancing every particle after every event. Virtual cells avoid all-pairs collision searches. These are not optional implementation decorations; they are central tests of whether an event-driven solution is genuinely scalable.",
      ["challenge/sources/bizon1998a.pdf", "challenge/sources/lubachevsky-1991-billiards.pdf", "harness/qualitative/RUBRIC.md"],
    );
  }

  // 12. Inelastic collapse
  {
    const slide = deck.slides.add();
    slide.background.fill = C.ink;
    addHeader(slide, "Inelasticity creates a numerical catastrophe.", 12, "INELASTIC COLLAPSE", true);
    addText(slide, "With a constant restitution coefficient, collision intervals can shrink geometrically.", {
      left: 46, top: 148, width: 980, height: 48,
    }, { size: 26, color: "#B9C8D1" });
    addLine(slide, 90, 370, 1080, 0, "#6B7B84", 2);
    const marks = [170, 430, 650, 830, 965, 1050, 1105, 1138, 1156, 1166];
    marks.forEach((x, index) => {
      addLine(slide, x, 320, 0, 100, index > 5 ? C.orange : C.cyan, index > 5 ? 5 : 3);
    });
    addText(slide, "Δt₁", { left: 245, top: 285, width: 80, height: 28 }, {
      size: 20, color: C.cyan, align: "center",
    });
    addText(slide, "Δt₂", { left: 505, top: 285, width: 80, height: 28 }, {
      size: 20, color: C.cyan, align: "center",
    });
    addText(slide, "Δtₙ → 0", { left: 1010, top: 270, width: 160, height: 34 }, {
      size: 23, color: C.orange, bold: true, align: "center",
    });
    addShape(slide, "roundRect", { left: 110, top: 500, width: 1030, height: 108 }, "#1D2C35", {
      style: "solid", fill: "#466579", width: 1,
    });
    addText(slide, "Infinitely many collisions occur in finite simulated time.", {
      left: 160, top: 533, width: 930, height: 48,
    }, { size: 34, color: C.white, bold: true, align: "center" });
    setNotes(
      slide,
      "This is inelastic collapse: a cluster undergoes an infinite sequence of ever-faster dissipative collisions before the simulation clock can advance beyond a finite time. A naive event queue can effectively freeze in this state.",
      ["challenge/sources/bizon1998a.pdf", "challenge/sources/marin-risso-cordero-1993.pdf"],
    );
  }

  // 13. Physical regularization
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "The paper regularizes collapse with a physical restitution law.", 13, "THE SOLUTION");
    addText(slide, "At low impact speed, collisions become nearly elastic.", {
      left: 48, top: 148, width: 720, height: 44,
    }, { size: 29, color: C.blue, bold: true });
    const plot = { x: 94, y: 252, w: 630, h: 320 };
    addLine(slide, plot.x, plot.y + plot.h, plot.w, 0, C.ink, 3);
    addLine(slide, plot.x, plot.y, 0, plot.h, C.ink, 3);
    addText(slide, "impact speed  |vₙ|", { left: plot.x + 220, top: plot.y + plot.h + 28, width: 240, height: 30 }, {
      size: 20, color: C.muted, align: "center",
    });
    addText(slide, "restitution  e", { left: 22, top: plot.y + 118, width: 120, height: 30 }, {
      size: 20, color: C.muted, align: "center",
    });
    addText(slide, "1", { left: 58, top: plot.y - 8, width: 22, height: 24 }, {
      size: 18, color: C.muted, align: "right",
    });
    const points = [];
    for (let i = 0; i <= 30; i += 1) {
      const t = i / 30;
      const e = 0.70 + 0.30 * Math.exp(-5.2 * t ** 0.75);
      points.push([plot.x + t * plot.w, plot.y + plot.h - e * plot.h]);
    }
    for (let i = 1; i < points.length; i += 1) {
      addLine(
        slide,
        points[i - 1][0],
        points[i - 1][1],
        points[i][0] - points[i - 1][0],
        points[i][1] - points[i - 1][1],
        C.orange,
        5,
      );
    }
    addLine(slide, plot.x, plot.y + plot.h * 0.30, plot.w, 0, C.line, 2, true);
    addText(slide, "high-speed value", { left: plot.x + 430, top: plot.y + 210, width: 190, height: 28 }, {
      size: 18, color: C.muted, align: "right",
    });
    addShape(slide, "roundRect", { left: 790, top: 225, width: 404, height: 332 }, C.paleOrange);
    addText(slide, "Why it works", { left: 824, top: 262, width: 280, height: 44 }, {
      size: 34, bold: true,
    });
    addBulletList(slide, [
      "Dissipation remains at ordinary collision speeds.",
      "Near-zero-speed impacts stop draining energy geometrically.",
      "The event clock can continue to advance.",
    ], { left: 826, top: 334, width: 320, height: 172 }, { size: 21, gap: 14 });
    addText(slide, "This is a model of material behavior, not an arbitrary timeout.", {
      left: 802, top: 584, width: 380, height: 56,
    }, { size: 21, color: C.orange, bold: true, align: "center" });
    setNotes(
      slide,
      "The paper uses a velocity-dependent coefficient of restitution that approaches one as the normal collision speed approaches zero. The exact low-speed approach is less important than eliminating the geometric dissipation that produces collapse.",
      ["challenge/sources/bizon1998a.pdf", "challenge/sources/marin-risso-cordero-1993.pdf"],
    );
  }

  // 14. Anecdote is not comparison
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "A single Fable result would be entertaining, not informative.", 14, "FROM DEMO TO BENCHMARK");
    addShape(slide, "roundRect", { left: 50, top: 170, width: 430, height: 390 }, C.paleBlue);
    addText(slide, "One run", { left: 84, top: 210, width: 240, height: 46 }, {
      size: 36, bold: true,
    });
    addText(slide, "“Fable made something that looks like granular patterns.”", {
      left: 86, top: 294, width: 340, height: 126,
    }, { size: 29, color: C.deepBlue, italic: true, lineSpacing: 1.08 });
    addText(slide, "Interesting anecdote", { left: 86, top: 484, width: 300, height: 34 }, {
      size: 23, color: C.muted, bold: true,
    });
    addArrow(slide, 508, 330, 118, 44, C.orange);
    addShape(slide, "roundRect", { left: 662, top: 170, width: 568, height: 390 }, C.panel);
    addText(slide, "Controlled comparison", { left: 698, top: 210, width: 430, height: 46 }, {
      size: 36, bold: true,
    });
    addBulletList(slide, [
      "Same paper and prompt",
      "Same tools and compute envelope",
      "Same output contract",
      "Same deterministic evaluator",
      "Same qualitative code review",
    ], { left: 704, top: 294, width: 438, height: 218 }, { size: 24, gap: 12 });
    addText(slide, "Evidence about model behavior", { left: 704, top: 522, width: 438, height: 32 }, {
      size: 23, color: C.blue, bold: true,
    });
    setNotes(
      slide,
      "The original impulse was to try Fable. But without other models and effort levels under the same conditions, there would be no basis for calling the result good, bad, or improved.",
    );
  }

  // 15. Effort uncertainty
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "More reasoning effort may help—or produce elaborate wrong turns.", 15, "A SECOND QUESTION");
    const levels = [
      { label: "LOW", x: 92, h: 130, fill: "#BBDDF1", text: "Moves quickly.\nMay miss the algorithm." },
      { label: "HIGH", x: 430, h: 230, fill: C.cyan, text: "More exploration.\nPotentially better reconstruction." },
      { label: "XHIGH / MAX", x: 768, h: 340, fill: C.blue, text: "More time and context.\nAlso more opportunity to rationalize a bad approach." },
    ];
    levels.forEach((level) => {
      const base = 562;
      addShape(slide, "roundRect", {
        left: level.x,
        top: base - level.h,
        width: 270,
        height: level.h,
      }, level.fill);
      addText(slide, level.label, {
        left: level.x + 20,
        top: base - level.h + 24,
        width: 230,
        height: 36,
      }, { size: 27, bold: true, color: level.label === "XHIGH / MAX" ? C.white : C.ink });
      addText(slide, level.text, {
        left: level.x + 20,
        top: base - level.h + 76,
        width: 230,
        height: level.h - 94,
      }, {
        size: 21,
        color: level.label === "XHIGH / MAX" ? "#E4F4FB" : C.deepBlue,
        lineSpacing: 1.12,
      });
    });
    addText(slide, "This is an empirical question, not a slogan about model quality.", {
      left: 98, top: 615, width: 950, height: 42,
    }, { size: 28, bold: true });
    setNotes(
      slide,
      "The campaign also tests a live concern in agent evaluation: the highest effort setting may improve careful implementation, but it may also encourage a model to overthink, improvise, or persist with a sophisticated wrong abstraction.",
    );
  }

  // 16. Campaign
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "So we threw the kitchen sink at one consistent challenge.", 16, "THE CAMPAIGN");
    addShape(slide, "roundRect", { left: 42, top: 152, width: 1196, height: 440 }, C.panel);
    addText(slide, "CODEX", { left: 78, top: 182, width: 160, height: 36 }, {
      size: 26, bold: true, color: C.blue,
    });
    addText(slide, "CLAUDE", { left: 690, top: 182, width: 160, height: 36 }, {
      size: 26, bold: true, color: C.orange,
    });
    addLine(slide, 640, 176, 0, 380, C.line, 2);
    const codexModels = [
      ["5.6 Sol", "low · xhigh"],
      ["5.6 Terra", "low · xhigh"],
      ["5.6 Luna", "low · xhigh"],
      ["5.5", "low · xhigh"],
      ["5.4", "low · xhigh"],
    ];
    const claudeModels = [
      ["Fable 5", "high"],
      ["Opus 5", "low · max"],
      ["Opus 4.8", "low · max"],
      ["Sonnet 5", "low · max"],
    ];
    codexModels.forEach(([model, effort], index) => {
      const y = 244 + index * 62;
      addShape(slide, "roundRect", { left: 78, top: y, width: 500, height: 46 }, C.white);
      addText(slide, model, { left: 98, top: y + 10, width: 220, height: 26 }, { size: 20, bold: true });
      addText(slide, effort, { left: 338, top: y + 10, width: 210, height: 26 }, {
        size: 19, color: C.muted, align: "right",
      });
    });
    claudeModels.forEach(([model, effort], index) => {
      const y = 244 + index * 72;
      addShape(slide, "roundRect", { left: 690, top: y, width: 500, height: 52 }, C.white);
      addText(slide, model, { left: 712, top: y + 13, width: 220, height: 27 }, { size: 21, bold: true });
      addText(slide, effort, { left: 958, top: y + 13, width: 200, height: 27 }, {
        size: 19, color: C.muted, align: "right",
      });
    });
    addText(slide, "17 runs · concurrency 2 · identical benchmark contract", {
      left: 300, top: 620, width: 680, height: 40,
    }, { size: 26, color: C.deepBlue, bold: true, align: "center" });
    setNotes(
      slide,
      "The campaign spans multiple model families and effort levels. The point is not that this is a definitive ranking, but that each result is generated under one explicit and reviewable contract.",
      ["campaigns/model-sweep.json"],
    );
  }

  // 17. No memory
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "Rule 1: every run starts newborn.", 17, "EXPERIMENTAL CONTROL");
    addShape(slide, "roundRect", { left: 72, top: 164, width: 420, height: 404 }, C.paleBlue);
    addText(slide, "Run N − 1", { left: 112, top: 206, width: 180, height: 36 }, {
      size: 27, bold: true, color: C.muted,
    });
    addShape(slide, "rect", { left: 120, top: 278, width: 310, height: 180 }, C.white, {
      style: "solid", fill: C.line, width: 1,
    });
    addText(slide, "code\ntranscript\nresults\nlessons", {
      left: 154, top: 306, width: 240, height: 124,
    }, { size: 25, color: C.muted, align: "center", lineSpacing: 1.12 });
    addShape(slide, "rect", { left: 555, top: 165, width: 88, height: 400 }, C.ink);
    addText(slide, "NO\nCARRY-\nOVER", { left: 566, top: 270, width: 66, height: 185 }, {
      size: 18, color: C.white, bold: true, align: "center", valign: "middle",
    });
    addShape(slide, "roundRect", { left: 706, top: 164, width: 500, height: 404 }, C.panel);
    addText(slide, "Run N", { left: 748, top: 206, width: 180, height: 36 }, {
      size: 27, bold: true,
    });
    addText(slide, "The agent receives:", { left: 750, top: 274, width: 280, height: 34 }, {
      size: 24, bold: true,
    });
    addBulletList(slide, [
      "The challenge prompt",
      "The specified paper and references",
      "The allowed runtime tools",
      "A clean workspace",
    ], { left: 754, top: 330, width: 380, height: 180 }, { size: 22, gap: 12 });
    addText(slide, "No previous code, transcript, result, or agent memory.", {
      left: 320, top: 610, width: 640, height: 40,
    }, { size: 27, color: C.blue, bold: true, align: "center" });
    setNotes(
      slide,
      "Each run must be independent. The agent container receives only the challenge inputs. It does not receive earlier submissions, model transcripts, local user configuration, or benchmark memory that could contaminate comparisons.",
      ["challenge/prompt.md", "harness/kubernetes/sterling/README.md"],
    );
  }

  // 18. No cheating
  {
    const slide = deck.slides.add();
    slide.background.fill = C.ink;
    addHeader(slide, "Rule 2: the agent cannot look up an implementation.", 18, "NO CHEATING", true);
    addText(slide, "An earlier interactive run quietly found the old C code on GitHub and used it.", {
      left: 54, top: 150, width: 820, height: 92,
    }, { size: 34, color: C.white, bold: true, lineSpacing: 1.02 });
    addShape(slide, "roundRect", { left: 54, top: 286, width: 500, height: 250 }, "#1D2C35", {
      style: "solid", fill: "#466579", width: 1,
    });
    addText(slide, "A reproduction can look excellent\nand still answer the wrong question.", {
      left: 90, top: 344, width: 430, height: 110,
    }, { size: 31, color: C.cyan, bold: true, align: "center", lineSpacing: 1.04 });
    addArrow(slide, 588, 380, 108, 42, C.orange);
    addShape(slide, "roundRect", { left: 730, top: 264, width: 460, height: 300 }, C.paleOrange);
    addText(slide, "The controlled version", { left: 768, top: 302, width: 370, height: 44 }, {
      size: 32, bold: true,
    });
    addBulletList(slide, [
      "No repository search",
      "No GitHub source access",
      "No hidden reference implementation",
      "Network policy enforced",
    ], { left: 774, top: 374, width: 340, height: 160 }, { size: 22, gap: 10 });
    addText(slide, "The paper is evidence. Existing code is leakage.", {
      left: 300, top: 615, width: 680, height: 40,
    }, { size: 28, color: C.white, bold: true, align: "center" });
    setNotes(
      slide,
      "This constraint comes from an actual failure mode. In a prior interactive attempt, the agent found an old implementation and used it without foregrounding that choice. That may reproduce the figure, but it does not test reconstruction from the paper.",
      ["challenge/prompt.md", "User-reported observation from an earlier interactive run"],
    );
  }

  // 19. Kubernetes architecture
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "Kubernetes turns those rules into infrastructure.", 19, "ISOLATED EXECUTION");
    const nodes = [
      { x: 46, w: 190, title: "Orchestrator", body: "launch\nrecover\ncollect", fill: C.paleBlue },
      { x: 286, w: 210, title: "Durable Job", body: "timeouts\nwatchdog\nstatus", fill: C.panel },
      { x: 546, w: 210, title: "Agent init", body: "paper\nprompt\ntools", fill: C.paleOrange },
      { x: 806, w: 190, title: "Evaluator", body: "reference\nmetrics\nreport", fill: C.paleGreen },
      { x: 1046, w: 190, title: "Artifacts", body: "manifest\nplots\nreview", fill: C.panel },
    ];
    nodes.forEach((node, index) => {
      addShape(slide, "roundRect", { left: node.x, top: 220, width: node.w, height: 250 }, node.fill);
      addText(slide, node.title, { left: node.x + 18, top: 250, width: node.w - 36, height: 46 }, {
        size: node.title === "Orchestrator" ? 22 : 27, bold: true, align: "center",
      });
      addText(slide, node.body, { left: node.x + 18, top: 324, width: node.w - 36, height: 112 }, {
        size: 22, color: C.muted, align: "center", lineSpacing: 1.14,
      });
      if (index < nodes.length - 1) addArrow(slide, node.x + node.w + 8, 325, 34, 28, C.deepBlue);
    });
    addShape(slide, "roundRect", { left: 285, top: 520, width: 712, height: 82 }, C.ink);
    addText(slide, "Persistent volume: code, outputs, transcript, evaluator products", {
      left: 316, top: 546, width: 650, height: 34,
    }, { size: 23, color: C.white, bold: true, align: "center" });
    addText(slide, "The untrusted agent never sees the trusted reference.", {
      left: 320, top: 630, width: 640, height: 36,
    }, { size: 25, color: C.blue, bold: true, align: "center" });
    setNotes(
      slide,
      "The orchestration layer launches durable Kubernetes Jobs with a persistent volume. The agent runs first in an isolated init container. Only after it exits does the trusted evaluator mount the reference artifacts and produce comparisons.",
      ["README.md", "harness/kubernetes/sterling/README.md", "harness/balls_bench/kubernetes.py"],
    );
  }

  // 20. Harness workflow
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "The harness separates generation from judgment.", 20, "THE EXPERIMENTAL LOOP");
    const steps = [
      ["1", "Agent builds", "Reads the paper, writes code, runs simulations, and submits trajectories plus a manifest."],
      ["2", "Harness checks", "Validates schemas, files, units, phases, shapes, and execution records deterministically."],
      ["3", "Evaluator compares", "Computes reference-relative metrics and renders plots, images, and time series."],
      ["4", "Reviewer judges", "A qualitative agent classifies the method and audits code, tests, and transcript decisions."],
    ];
    steps.forEach(([number, title, body], index) => {
      const x = 42 + index * 306;
      const accent = [C.blue, C.deepBlue, C.green, C.orange][index];
      addShape(slide, "roundRect", { left: x, top: 168, width: 270, height: 394 }, C.panel);
      addText(slide, number, { left: x + 22, top: 192, width: 54, height: 50 }, {
        size: 38, bold: true, color: accent,
      });
      addText(slide, title, { left: x + 22, top: 266, width: 226, height: 70 }, {
        size: 31, bold: true,
      });
      addText(slide, body, { left: x + 22, top: 365, width: 226, height: 154 }, {
        size: 21, color: C.muted, lineSpacing: 1.12,
      });
      if (index < 3) addArrow(slide, x + 274, 346, 28, 25, C.deepBlue);
    });
    addText(slide, "The agent is not allowed to grade itself.", {
      left: 340, top: 620, width: 600, height: 40,
    }, { size: 29, color: C.blue, bold: true, align: "center" });
    setNotes(
      slide,
      "The executing agent's job is to produce code and simulation outputs. The harness, not the agent, decides how those outputs compare with the reference. The resulting report preserves deterministic evidence and a separate qualitative review.",
      ["README.md", "challenge/prompt.md", "harness/balls_bench/evaluator.py", "harness/balls_bench/viewer.py"],
    );
  }

  // 21. Deterministic evaluator
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "The deterministic evaluator asks whether the outputs behave alike.", 21, "QUANTITATIVE EVIDENCE");
    const groups = [
      ["PATTERN", "contrast\nwavelength\nQ₂ · Q₄ · Q₆", C.paleBlue, C.blue],
      ["TIMING", "phase alignment\nf/2 vs f/4\ntemporal correlation", C.panel, C.deepBlue],
      ["DYNAMICS", "COM height\nvelocity\nspin · energy", C.paleGreen, C.green],
      ["CONTACT", "collision rate\nprecision-\nqualified overlaps", C.paleOrange, C.orange],
    ];
    groups.forEach(([title, body, fill, accent], index) => {
      const x = 42 + index * 306;
      addShape(slide, "roundRect", { left: x, top: 174, width: 270, height: 340 }, fill);
      addShape(slide, "rect", { left: x, top: 174, width: 270, height: 12 }, accent);
      addText(slide, title, { left: x + 24, top: 214, width: 222, height: 34 }, {
        size: 23, bold: true, color: accent,
      });
      addText(slide, body, { left: x + 24, top: 286, width: 222, height: 164 }, {
        size: title === "CONTACT" ? 24 : 26, bold: true, lineSpacing: 1.16,
      });
    });
    addShape(slide, "roundRect", { left: 170, top: 562, width: 940, height: 70 }, C.ink);
    addText(slide, "Reference and submission are processed by the same metric code.", {
      left: 210, top: 582, width: 860, height: 34,
    }, { size: 25, color: C.white, bold: true, align: "center" });
    setNotes(
      slide,
      "The quantitative layer compares patterns, phase behavior, bulk dynamics, velocities and spins, collision rates, and physically meaningful overlaps. It also renders the images and time-series comparisons that make unexpected behavior inspectable.",
      ["harness/METRICS.md", "harness/balls_bench/metrics.py", "harness/balls_bench/evaluator.py"],
    );
  }

  // 22. Qualitative evaluator
  {
    const slide = deck.slides.add();
    slide.background.fill = C.paper;
    addHeader(slide, "The qualitative evaluator asks what the agent actually built.", 22, "CODE AND TRANSCRIPT REVIEW");
    addShape(slide, "roundRect", { left: 44, top: 154, width: 490, height: 470 }, C.panel);
    addText(slide, "First: classify the simulation", { left: 76, top: 186, width: 400, height: 42 }, {
      size: 29, bold: true,
    });
    const classes = [
      "Event-driven hard-sphere MD",
      "Time-stepped hard-sphere MD",
      "Soft-sphere time-stepped MD",
      "Wave equation / image-fit model",
      "Something else",
    ];
    classes.forEach((label, index) => {
      const y = 258 + index * 58;
      addShape(slide, "roundRect", { left: 78, top: y, width: 408, height: 42 }, index === 0 ? C.paleGreen : C.white);
      addText(slide, label, { left: 94, top: y + 9, width: 374, height: 24 }, {
        size: 19, bold: index === 0, color: index === 0 ? C.green : C.ink,
      });
    });
    addText(slide, "The rest of the rubric is gated by that answer.", {
      left: 94, top: 566, width: 370, height: 40,
    }, { size: 19, color: C.muted, italic: true, align: "center" });

    addShape(slide, "roundRect", { left: 574, top: 154, width: 664, height: 470 }, C.paleBlue);
    addText(slide, "Then: audit the implementation and process", {
      left: 610, top: 186, width: 560, height: 42,
    }, { size: 29, bold: true });
    const audit = [
      ["Event mechanics", "queue, invalidation, free flight, moving plate"],
      ["Scalability", "delayed states, virtual cells, local rescheduling"],
      ["Dense behavior", "collapse regularization, overlap handling"],
      ["Tests", "collision response, prediction, sequencing, boundaries"],
      ["Transcript", "major decisions, waiting time, retries, subscription stalls"],
    ];
    audit.forEach(([title, body], index) => {
      const y = 256 + index * 64;
      addText(slide, title, { left: 614, top: y, width: 180, height: 28 }, {
        size: 20, bold: true, color: C.deepBlue,
      });
      addText(slide, body, { left: 808, top: y, width: 380, height: 42 }, {
        size: 19, color: C.muted,
      });
      if (index < audit.length - 1) addLine(slide, 614, y + 47, 574, 0, "#C7DCE7", 1);
    });
    setNotes(
      slide,
      "Classification comes first because later questions depend on the model type. An image-fitting wave model should not receive credit for event queue correctness, and an event-driven implementation must be examined for delayed states, virtual cells, collision sequencing, and collapse regularization.",
      ["harness/qualitative/RUBRIC.md", "harness/qualitative/README.md"],
    );
  }

  // 23. Closing
  {
    const slide = deck.slides.add();
    slide.background.fill = C.ink;
    addText(slide, "The benchmark asks two different questions.", {
      left: 72, top: 72, width: 900, height: 72,
    }, { size: 50, color: C.white, bold: true });
    addShape(slide, "roundRect", { left: 72, top: 202, width: 530, height: 300 }, "#1D2C35", {
      style: "solid", fill: "#466579", width: 1,
    });
    addText(slide, "1", { left: 108, top: 236, width: 60, height: 60 }, {
      size: 48, color: C.cyan, bold: true,
    });
    addText(slide, "Did it reproduce\nthe patterns?", {
      left: 108, top: 326, width: 430, height: 110,
    }, { size: 39, color: C.white, bold: true, lineSpacing: 1.0 });
    addShape(slide, "roundRect", { left: 678, top: 202, width: 530, height: 300 }, C.paleOrange);
    addText(slide, "2", { left: 714, top: 236, width: 60, height: 60 }, {
      size: 48, color: C.orange, bold: true,
    });
    addText(slide, "Did it build\nthe right physics?", {
      left: 714, top: 326, width: 430, height: 110,
    }, { size: 39, color: C.ink, bold: true, lineSpacing: 1.0 });
    addText(slide, "The interesting results are where those answers disagree.", {
      left: 190, top: 578, width: 900, height: 54,
    }, { size: 31, color: C.cyan, bold: true, align: "center" });
    addText(slide, "23", { left: 1182, top: 650, width: 56, height: 22 }, {
      size: 15, color: "#B9C8D1", align: "right",
    });
    setNotes(
      slide,
      "Close on the benchmark's core distinction. A model may make plausible patterns with the wrong algorithm, or implement the correct algorithm but fail to reach the target state. Both are scientifically meaningful outcomes, and the harness is designed to preserve the evidence needed to tell them apart.",
    );
  }

  return deck;
}


async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}


async function main() {
  const deck = await buildDeck();
  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    const png = await deck.export({ slide, format: "png", scale: 1 });
    await writeBlob(path.join(RENDERED, `${stem}.png`), png);
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(RENDERED, `${stem}.layout.json`), await layout.text());
  }
  const montage = await deck.export({ format: "webp", montage: true, scale: 0.5 });
  await writeBlob(path.join(RENDERED, "deck-montage.webp"), montage);
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(OUTPUT);
  console.log(OUTPUT);
}


main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
