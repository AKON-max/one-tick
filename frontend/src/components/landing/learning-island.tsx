"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, OrbitControls } from "@react-three/drei";
import { BufferGeometry, Color, DoubleSide, Float32BufferAttribute, type Group } from "three";

// ── 小单元、绵密感 ──
const UNIT = 0.34;
const GRID_X = { min: -12, max: 12 };
const GRID_Z = { min: -8, max: 8 };
const INITIAL_TILES = 150;
const TILES_PER_CHECKIN = 5;

type TileKind = "forest" | "moss" | "water" | "rock" | "river" | "village" | "waterfall";

type Tile = {
  x: number;
  z: number;
  height: number;
  elevation: number; // 海拔 — 高则浮空，低则下陷
  delay: number;
  kind: TileKind;
  unlockOrder: number;
};

type SceneType = "rain" | "snow" | "cloud";

// ── 场景调色板接口（新增 sceneLight 双场色 + villageTop 收归） ──
interface ScenePalette {
  treeTrunk: string;
  treeCrown1: string;
  treeCrown2: string;
  treeCrown3: string;
  treeCrown4: string;
  mountain1: string;
  mountain2: string;
  mountainSnow: string;
  fern1: string;
  fern2: string;
  rock1: string;
  rock2: string;
  pond: string;
  pondFlower: string;
  waterTop: string;
  rockTop: string;
  mossTop: string;
  forestTop: string;
  tileSide: string;
  riverTop: string;
  riverEmissive: string;
  villageWall: string;
  villageRoof: string;
  villageTop: string;
  sceneSky: string;
  sceneGround: string;
  sceneIntensity: number;
}

// ── 雨林调色板（原 PALETTE + 补 villageTop 与场景光） ──
const PALETTE_RAIN: ScenePalette = {
  treeTrunk: "#6b5a3e",
  treeCrown1: "#4d9e6a",
  treeCrown2: "#5ead78",
  treeCrown3: "#6dbf8a",
  treeCrown4: "#82cf9d",
  mountain1: "#4d8a6a",
  mountain2: "#5e9a78",
  mountainSnow: "#98c9a8",
  fern1: "#55a870",
  fern2: "#6dbd85",
  rock1: "#5e8a6e",
  rock2: "#789d80",
  pond: "#6ec98a",
  pondFlower: "#e8bbc8",
  waterTop: "#5ab8b0",
  rockTop: "#649075",
  mossTop: "#6dbd85",
  forestTop: "#5eaa78",
  tileSide: "#244839",
  riverTop: "#3b9ec8",
  riverEmissive: "#0a2a3a",
  villageWall: "#d4c8a8",
  villageRoof: "#c47a4a",
  villageTop: "#8a9e7a",
  sceneSky: "#d4f0e0",
  sceneGround: "#0d241a",
  sceneIntensity: 1.3,
};

// ── 雪景调色板（雪山 + 盖雪欧洲小镇，灰蓝 + 暖木屋） ──
const PALETTE_SNOW: ScenePalette = {
  treeTrunk: "#7a6e62",
  treeCrown1: "#f4f8fb",
  treeCrown2: "#e4eaf0",
  treeCrown3: "#d0dae6",
  treeCrown4: "#c0cee0",
  mountain1: "#6a7a8c",
  mountain2: "#5a6a7c",
  mountainSnow: "#f8faff",
  fern1: "#d0dae6",
  fern2: "#e4eaf0",
  rock1: "#5a6a7c",
  rock2: "#7a8a9c",
  pond: "#c0cee0",
  pondFlower: "#e4eaf0",
  waterTop: "#9ab0c8",
  rockTop: "#d0dae6",
  mossTop: "#e4eaf0",
  forestTop: "#d8e2ee",
  tileSide: "#2e3e4e",
  riverTop: "#d0dae6",
  riverEmissive: "#1a2a38",
  villageWall: "#e8ddd0",
  villageRoof: "#a89888",
  villageTop: "#f0f4f8",
  sceneSky: "#f0f5f9",
  sceneGround: "#1e2e3e",
  sceneIntensity: 1.22,
};

// ── 暖云调色板（欧洲小镇 + 云层山脉，米白 + 暖陶瓦） ──
const PALETTE_CLOUD: ScenePalette = {
  treeTrunk: "#8a7a62",
  treeCrown1: "#faf4e4",
  treeCrown2: "#f2e8cc",
  treeCrown3: "#e8dcba",
  treeCrown4: "#dcd0a6",
  mountain1: "#8a9aaa",
  mountain2: "#a0aeb8",
  mountainSnow: "#fefcf4",
  fern1: "#d8dfc4",
  fern2: "#e8ecd4",
  rock1: "#aaa08a",
  rock2: "#c4bca6",
  pond: "#c8d6de",
  pondFlower: "#f0dcd4",
  waterTop: "#9ab4c4",
  rockTop: "#e4dcc8",
  mossTop: "#f0e8d2",
  forestTop: "#d4dcb8",
  tileSide: "#3e3a2e",
  riverTop: "#a8c0d0",
  riverEmissive: "#2a2e34",
  villageWall: "#f4ead4",
  villageRoof: "#b0784a",
  villageTop: "#f0e4cc",
  sceneSky: "#faf4e4",
  sceneGround: "#3a362e",
  sceneIntensity: 1.28,
};

// ── Context：子组件（Tree / Fern / Rock / TileMesh 等）统一读 palette ──
const PaletteContext = createContext<ScenePalette>(PALETTE_RAIN);
function usePalette(): ScenePalette {
  return useContext(PaletteContext);
}

// ── DOM data-scene → palette ──
function paletteForScene(scene: string | null | undefined): ScenePalette {
  if (scene === "snow") return PALETTE_SNOW;
  if (scene === "cloud") return PALETTE_CLOUD;
  return PALETTE_RAIN;
}
function readSceneFromDOM(): SceneType {
  if (typeof document === "undefined") return "rain";
  const v = document.documentElement.dataset.scene as SceneType | undefined;
  return v === "snow" || v === "cloud" ? v : "rain";
}

// ── 生成所有 tile ──
const allTilesRaw: Array<{ x: number; z: number }> = [];
for (let z = GRID_Z.min; z <= GRID_Z.max; z++) {
  for (let x = GRID_X.min; x <= GRID_X.max; x++) {
    const ex = x / (GRID_X.max + 1);
    const ez = z / (GRID_Z.max + 1);
    if (ex * ex + ez * ez > 1.05) continue;
    allTilesRaw.push({ x, z });
  }
}

// ── 解锁顺序：不随机打洞，而是从岛心一圈圈向外解锁 ──
// 这样任何时刻已解锁的地块都是一整块连成片的陆地，中间不会出现"空块"。
//（具体排序在 tiles 生成之后执行，见下方 islandOrder）

// ── 噪声函数 ──
function noise2D(x: number, z: number, seed: number): number {
  return Math.sin(x * 0.37 + seed) * Math.cos(z * 0.41 + seed * 1.3);
}

// ── 河流路径：蛇形穿越岛屿 ──
function isOnRiver(x: number, z: number): boolean {
  const riverCenter = Math.sin(x * 0.22) * 3.5 + Math.sin(x * 0.13 + 1.5) * 2 + Math.cos(x * 0.08) * 1.5;
  return Math.abs(z - riverCenter) < 0.85;
}
const riverCells = new Set<string>();
for (const { x, z } of allTilesRaw) {
  if (isOnRiver(x, z)) riverCells.add(`${x},${z}`);
}

// ── 村庄：河流旁的低地小聚落 ──
const villageCoords = [
  [-3, -1], [-2, -2], [-1, -1],  // 左岸村落
  [4, 1], [5, 0], [4, 2],         // 右岸村落
];
const villageCells = new Set(villageCoords.map(([x, z]) => `${x},${z}`));

// ── 瀑布：河流上 3 处落差点 ──
const waterfallCoords = [
  [-5, -1], [1, 2], [7, -2],
];
const waterfallCells = new Set(waterfallCoords.map(([x, z]) => `${x},${z}`));

// ── 村庄周围的平原（砍掉高树） ──
const villageClearing = new Set<string>();
for (const [vx, vz] of villageCoords) {
  for (let dx = -1; dx <= 1; dx++) {
    for (let dz = -1; dz <= 1; dz++) {
      villageClearing.add(`${vx + dx},${vz + dz}`);
    }
  }
}

function cellKind(key: string, x: number, z: number): TileKind {
  if (waterfallCells.has(key)) return "waterfall";
  if (riverCells.has(key)) return "river";
  if (villageCells.has(key)) return "village";
  // 村庄周围清成苔藓平原，不种高树
  if (villageClearing.has(key)) return "moss";
  const h = ((x * 17 + z * 31 + 100) % 101);
  if (h < 6) return "water";
  if (h < 18) return "rock";
  if (h < 38) return "moss";
  return "forest";
}

const tiles: Tile[] = allTilesRaw.map(({ x, z }) => {
  const key = `${x},${z}`;
  const kind = cellKind(key, x, z);

  // 到中心的归一化距离（0=中心, 1=边缘）
  const ex = x / (GRID_X.max + 1);
  const ez = z / (GRID_Z.max + 1);
  const distFromCenter = Math.hypot(ex, ez);

  // 平缓的中心隆起（低幅、低频）→ 地块之间高度差小，连成一片土地
  const centerDome = Math.max(0, 1 - distFromCenter) * 0.9;
  const rimRamp = Math.max(0, 1 - distFromCenter * 0.55) * 0.18;

  // 只用低频缓坡做起伏，避免相邻地块出现断层/悬崖
  const n1 = noise2D(x, z, 0) * 0.13;
  const n2 = noise2D(x, z, 5) * 0.11;
  const n3 = Math.sin(x * 0.25 + z * 0.3) * Math.cos(z * 0.2 - x * 0.15) * 0.1;
  const n4 = Math.abs(noise2D(x, z, 10)) * 0.07;

  // 合成海拔：缓坡山丘，无浮空
  let rawElevation = centerDome + rimRamp + n1 + n2 + n3 + n4 - distFromCenter * 0.08;

  // 村庄区域压平，让木屋露出来
  if (villageClearing.has(key)) {
    rawElevation = 0.15;
  } else if (villageCoords.some(([vx, vz]) => Math.abs(x - vx) <= 2 && Math.abs(z - vz) <= 2)) {
    // 村庄外一圈柔和过渡
    rawElevation = rawElevation * 0.35 + 0.1;
  }

  const elevation = kind === "water" ? rawElevation - 0.4
    : kind === "river" || kind === "waterfall" ? rawElevation - 0.25
    : Math.round(rawElevation * 100) / 100;

  // 柱体厚度完全统一：不再暴露高矮不一的侧壁，块面像铺开的地皮
  const height = 0.18;

  const delay = 0.02 + distFromCenter * 0.05;

  return {
    x,
    z,
    height,
    elevation,
    delay,
    kind,
    unlockOrder: 0, // 稍后按“离岛心由近及远”回填
  };
});

const totalTiles = tiles.length;

// ── 从岛心一圈圈向外：保证已解锁地块永远是连成片的大陆 ──
// 注意：用“归一化半径”排序（与地形圆丘同一套度量），
// 这样解锁边界是沿着“等高山脊”走的，崖壁一圈高度齐平、不会有锯齿尖刺。
const islandOrder = [...tiles].sort((a, b) => {
  const na = Math.hypot(a.x / (GRID_X.max + 1), a.z / (GRID_Z.max + 1));
  const nb = Math.hypot(b.x / (GRID_X.max + 1), b.z / (GRID_Z.max + 1));
  if (na !== nb) return na - nb;
  const aa = Math.atan2(a.z, a.x);
  const ab = Math.atan2(b.z, b.x);
  if (aa !== ab) return aa - ab;
  return a.x - b.x || a.z - b.z;
});
islandOrder.forEach((t, i) => (t.unlockOrder = i + 1));
const islandKey = (t: Tile) => `${t.x},${t.z}`;

// ── 种树位：forest 地块按“离岛心由近及远”稳定排序 ──
// 树的棵数 = 打卡天数；第 k 天种的树落在第 k 个种树位上（近处先种，向外扩散）
const forestSlots = tiles
  .filter((t) => t.kind === "forest")
  .sort(
    (a, b) =>
      (Math.hypot(a.x, a.z) - Math.hypot(b.x, b.z)) ||
      a.x - b.x ||
      a.z - b.z
  );
const forestSlotOf = new Map(
  forestSlots.map((t, i) => [`${t.x},${t.z}`, i + 1])
);

// ============================================================
// ── 连续地形：一整张平滑网格取代“一格格方块柱” ──
// 网格顶点在相邻地块交界处共享同一高度，地块之间不再有缝隙、台阶与空块。
// ============================================================

const cellByKey = new Map<string, Tile>();
tiles.forEach((t) => cellByKey.set(islandKey(t), t));

// 网格顶点：(vx, vz) 表示地块 (vx,vz)/(vx+1,vz)/(vx,vz+1)/(vx+1,vz+1) 的交点，
// 世界坐标为 ((vx+0.5)*UNIT, ·, (vz+0.5)*UNIT)。
// 高度 = 相邻地块海拔的平均值；靠岛边的顶点会自然下沉成缓坡海岸。
const vertexYCache = new Map<string, number>();
function vertexY(vx: number, vz: number): number {
  const key = `${vx},${vz}`;
  const cached = vertexYCache.get(key);
  if (cached !== undefined) return cached;
  let sum = 0;
  let n = 0;
  for (const cx of [vx, vx + 1]) {
    for (const cz of [vz, vz + 1]) {
      const cell = cellByKey.get(`${cx},${cz}`);
      if (!cell) continue;
      sum += cell.elevation;
      n += 1;
    }
  }
  let h = n > 0 ? sum / n : 0;
  const missing = 4 - n;
  if (missing > 0) h -= 0.03 + missing * 0.06; // 海岸缓坡：外边地块略微下垂
  vertexYCache.set(key, h);
  return h;
}

// 地块中心的地表高度（放树/房子/草丛时脚踩在这里，保证贴地不悬空）
function surfaceYOf(t: Tile): number {
  const { x, z } = t;
  return (
    (vertexY(x - 1, z - 1) + vertexY(x, z - 1) + vertexY(x - 1, z) + vertexY(x, z)) /
    4
  );
}

// 每个地块的“地表颜色”→ 由四种地块类型着色，让整张网格有自然的土地色块
function groundColorOf(kind: TileKind, palette: ScenePalette): string {
  switch (kind) {
    case "water": return palette.pond;
    case "river":
    case "waterfall": return palette.riverTop;
    case "rock": return palette.rockTop;
    case "village": return palette.villageTop;
    case "moss": return palette.mossTop;
    default: return palette.forestTop;
  }
}

// 岛体“悬崖”厚度：顶面往下这么深，形成一圈实心侧壁
const CLIFF_DEPTH = 0.42;
// 崖壁统一浅沙色（不随雨/雪/云场景切换，保证三种风格下都是干净的土崖色）
const CLIFF_COLOR = "#d9c8a0";
// 归一化坐标系：X/Z 各除以各自的半宽，让“圆”在地图上是正圆（与地形起伏同一套度量）
const NORM_X = GRID_X.max + 1; // =13
const NORM_Z = GRID_Z.max + 1; // =9
const ISLAND_RHO = Math.sqrt(1.05); // 生成岛屿掩码时的外接圆半径
const CELL_REACH = Math.hypot(0.5 / NORM_X, 0.5 / NORM_Z); // 半格对角（归一化）

// 已解锁格子数 → 当前海岸圆半径：取最外层格子中心 + 半格，让圆能“切开”边缘格子
function rhoForUnlocked(n: number): number {
  if (n <= 0) return 0;
  const last = islandOrder[Math.min(n - 1, islandOrder.length - 1)];
  const d = Math.hypot(last.x / NORM_X, last.z / NORM_Z);
  return Math.min(d + CELL_REACH, ISLAND_RHO);
}

type PV = { x: number; y: number; z: number; u: number; v: number };

// 把每个地块的多边形用平滑圆裁剪 → 海岸线是连续圆弧，不是“楼梯格锯齿”
function clipToCircle(poly: PV[], rho: number): PV[] {
  const r2 = rho * rho;
  const inside = (p: PV) => p.u * p.u + p.v * p.v <= r2;
  const out: PV[] = [];
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length];
    const ain = inside(a);
    if (ain) out.push(a);
    if (ain !== inside(b)) {
      // 线段与圆求交（只可能穿过一次）
      const du = b.u - a.u;
      const dv = b.v - a.v;
      const qa = du * du + dv * dv;
      const qb = 2 * (a.u * du + a.v * dv);
      const qc = a.u * a.u + a.v * a.v - r2;
      const disc = Math.sqrt(Math.max(0, qb * qb - 4 * qa * qc));
      let t = (-qb - disc) / (2 * qa);
      if (t < 0 || t > 1) t = (-qb + disc) / (2 * qa);
      out.push({
        u: a.u + du * t,
        v: a.v + dv * t,
        x: a.x + (b.x - a.x) * t,
        y: a.y + (b.y - a.y) * t,
        z: a.z + (b.z - a.z) * t,
      });
    }
  }
  // 去掉相邻重复点（圆恰好过角点等退化情况）
  return out.filter((p, i) => {
    if (i === 0) return true;
    const q = out[i - 1];
    return Math.abs(p.x - q.x) > 1e-7 || Math.abs(p.z - q.z) > 1e-7;
  });
}

// 实心岛体：顶面（圆裁剪的连续地形）+ 沿弧线的沙色悬崖 + 整体下移的封底
// 材质使用 DoubleSide，三角形绕序无需额外校验。
function buildTerrainGeometry(
  rho: number,
  palette: ScenePalette
): BufferGeometry {
  const positions: number[] = [];
  const colors: number[] = [];
  const c = new Color();

  const corner = (vx: number, vz: number): PV => ({
    x: (vx + 0.5) * UNIT,
    y: vertexY(vx, vz),
    z: (vz + 0.5) * UNIT,
    u: (vx + 0.5) / NORM_X,
    v: (vz + 0.5) / NORM_Z,
  });

  // 把多边形 fan 成三角形（dy：整体下移量，用于封底）
  const emitFan = (poly: PV[], dy: number) => {
    for (let i = 1; i + 1 < poly.length; i++) {
      for (const p of [poly[0], poly[i], poly[i + 1]]) {
        positions.push(p.x, p.y + dy, p.z);
        colors.push(c.r, c.g, c.b);
      }
    }
  };

  const pushColor = (hex: string) => {
    c.set(hex);
  };

  for (const t of tiles) {
    const cx = t.x / NORM_X;
    const cz = t.z / NORM_Z;
    // 整块都在圆外 → 跳过
    if (Math.hypot(cx, cz) - CELL_REACH > rho) continue;

    const quad = [
      corner(t.x - 1, t.z - 1),
      corner(t.x, t.z - 1),
      corner(t.x, t.z),
      corner(t.x - 1, t.z),
    ];
    const poly = clipToCircle(quad, rho);
    if (poly.length < 3) continue;

    // ① 顶面
    pushColor(groundColorOf(t.kind, palette));
    emitFan(poly, 0);

    // ② 封底（整片下移）
    pushColor(CLIFF_COLOR);
    emitFan(poly, -CLIFF_DEPTH);

    // ③ 沿“圆上弧边”的悬崖侧壁（两端都在圆上的边 = 海岸线）
    pushColor(CLIFF_COLOR);
    const onCircle = (p: PV) =>
      Math.abs(Math.hypot(p.u, p.v) - rho) < 1e-3;
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i];
      const b = poly[(i + 1) % poly.length];
      if (!onCircle(a) || !onCircle(b)) continue;
      const ay = a.y - CLIFF_DEPTH;
      const by = b.y - CLIFF_DEPTH;
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z, a.x, ay, a.z);
      colors.push(c.r, c.g, c.b, c.r, c.g, c.b, c.r, c.g, c.b);
      positions.push(a.x, ay, a.z, b.x, b.y, b.z, b.x, by, b.z);
      colors.push(c.r, c.g, c.b, c.r, c.g, c.b, c.r, c.g, c.b);
    }
  }

  const geo = new BufferGeometry();
  geo.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geo.setAttribute("color", new Float32BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  return geo;
}

// ============================================================
// ── 装饰组件（按新比例缩小） ──
// ============================================================

function NewTileSparkle({ color }: { color: string }) {
  const group = useRef<Group>(null);
  useFrame((state) => {
    if (!group.current) return;
    const t = state.clock.elapsedTime;
    group.current.children.forEach((child, i) => {
      if (i === 0) return;
      const offset = Math.sin(t * 2.0 + i * 0.9) * (0.05 + (i % 3) * 0.03);
      child.position.y = 0.16 + offset;
    });
    const breathe = 1 + Math.sin(t * 1.2) * 0.1;
    group.current.scale.setScalar(breathe);
    const ring = group.current.children[0];
    if (ring) ring.rotation.z += 0.004;
  });
  return (
    <group ref={group}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
        <ringGeometry args={[0.14, 0.22, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.7} side={2} />
      </mesh>
      <mesh position={[0, 0.11, 0]}>
        <sphereGeometry args={[0.04, 6, 4]} />
        <meshBasicMaterial color="#fffef0" transparent opacity={0.9} />
      </mesh>
      <mesh position={[0, 0.1, 0]}>
        <sphereGeometry args={[0.08, 6, 4]} />
        <meshBasicMaterial color={color} transparent opacity={0.3} />
      </mesh>
      {Array.from({ length: 6 }).map((_, i) => {
        const angle = (i / 6) * Math.PI * 2;
        const radius = 0.2;
        return (
          <mesh key={i} position={[Math.cos(angle) * radius, 0.16, Math.sin(angle) * radius]}>
            <sphereGeometry args={[0.035, 5, 3]} />
            <meshBasicMaterial color="#fffbe6" transparent opacity={0.85} />
          </mesh>
        );
      })}
    </group>
  );
}

function TinyTree({ variant }: { variant: number }) {
  const palette = usePalette();
  const crown = useRef<Group>(null);
  useFrame((state) => {
    if (!crown.current) return;
    crown.current.rotation.z = Math.sin(state.clock.elapsedTime * 0.85 + variant * 0.7) * 0.03;
    crown.current.rotation.x = Math.cos(state.clock.elapsedTime * 0.7 + variant) * 0.015;
  });
  const tall = variant % 3 === 0;
  const s = tall ? 1.05 : 0.82;
  return (
    <group scale={s}>
      <mesh castShadow position={[0, 0.2, 0]}>
        <cylinderGeometry args={[0.03, 0.05, 0.4, 5]} />
        <meshStandardMaterial color={palette.treeTrunk} roughness={1} />
      </mesh>
      <group ref={crown} position={[0, 0.4, 0]}>
        <mesh castShadow position={[0, 0.04, 0]}>
          <icosahedronGeometry args={[0.18, 0]} />
          <meshStandardMaterial color={palette.treeCrown1} flatShading roughness={0.94} />
        </mesh>
        <mesh castShadow position={[-0.12, -0.01, 0.02]}>
          <icosahedronGeometry args={[0.14, 0]} />
          <meshStandardMaterial color={palette.treeCrown2} flatShading roughness={0.92} />
        </mesh>
        <mesh castShadow position={[0.12, 0, -0.02]}>
          <icosahedronGeometry args={[0.13, 0]} />
          <meshStandardMaterial color={palette.treeCrown3} flatShading roughness={0.92} />
        </mesh>
        <mesh castShadow position={[0.03, 0.18, 0.01]}>
          <icosahedronGeometry args={[0.12, 0]} />
          <meshStandardMaterial color={palette.treeCrown4} flatShading roughness={0.9} />
        </mesh>
      </group>
    </group>
  );
}

function TinyMountain({ variant }: { variant: number }) {
  const palette = usePalette();
  const h = 0.5 + (variant % 3) * 0.1;
  return (
    <group>
      <mesh castShadow position={[0, h / 2, 0]} rotation={[0, variant * 0.42, 0]}>
        <coneGeometry args={[0.22, h, 5]} />
        <meshStandardMaterial color={palette.mountain1} flatShading roughness={1} />
      </mesh>
      <mesh castShadow position={[0.12, h * 0.34, 0.05]} rotation={[0, 0.5, 0]}>
        <coneGeometry args={[0.13, h * 0.6, 5]} />
        <meshStandardMaterial color={palette.mountain2} flatShading roughness={1} />
      </mesh>
      <mesh castShadow position={[-0.05, h - 0.05, 0]} rotation={[0, variant * 0.42, 0]}>
        <coneGeometry args={[0.06, 0.12, 5]} />
        <meshStandardMaterial color={palette.mountainSnow} flatShading roughness={0.95} />
      </mesh>
    </group>
  );
}

function TinyFern({ variant }: { variant: number }) {
  const palette = usePalette();
  return (
    <group rotation={[0, variant * 0.65, 0]}>
      {[0, 1, 2, 3, 4].map((leaf) => (
        <mesh
          key={leaf}
          castShadow
          position={[Math.cos(leaf * 1.26) * 0.06, 0.06, Math.sin(leaf * 1.26) * 0.06]}
          rotation={[0.35, -leaf * 1.26, 0.65]}
        >
          <coneGeometry args={[0.032, 0.17, 4]} />
          <meshStandardMaterial color={leaf % 2 ? palette.fern1 : palette.fern2} flatShading roughness={1} />
        </mesh>
      ))}
    </group>
  );
}

/** 低矮草丛/碎石：用来填充空地，避免出现"光秃秃的空方块" */
function TinyTuft({ variant }: { variant: number }) {
  const palette = usePalette();
  const blades = 2 + ((variant * 7) % 3); // 2~4 簇
  return (
    <group rotation={[0, variant * 1.7, 0]}>
      {Array.from({ length: blades }).map((_, i) => {
        const angle = (i / blades) * Math.PI * 2;
        const r = 0.035 + ((variant + i) % 3) * 0.02;
        const isStone = ((variant + i) * 13) % 4 === 0;
        if (isStone) {
          return (
            <mesh key={i} castShadow position={[Math.cos(angle) * r, 0.03, Math.sin(angle) * r]} scale={[1, 0.7, 0.85]}>
              <dodecahedronGeometry args={[0.028, 0]} />
              <meshStandardMaterial color={palette.rock2} flatShading roughness={1} />
            </mesh>
          );
        }
        return (
          <mesh
            key={i}
            castShadow
            position={[Math.cos(angle) * r, 0.035, Math.sin(angle) * r]}
            rotation={[0.12, i * 1.3, 0.3 + (i % 2) * 0.4]}
          >
            <coneGeometry args={[0.02, 0.1, 4]} />
            <meshStandardMaterial color={i % 2 ? palette.fern2 : palette.fern1} flatShading roughness={1} />
          </mesh>
        );
      })}
    </group>
  );
}

function TinyRock({ variant }: { variant: number }) {
  const palette = usePalette();
  return (
    <group rotation={[0, variant * 0.8, 0]}>
      <mesh castShadow position={[0, 0.08, 0]} scale={[1, 0.72, 0.82]}>
        <dodecahedronGeometry args={[0.13, 0]} />
        <meshStandardMaterial color={palette.rock1} flatShading roughness={1} />
      </mesh>
      <mesh castShadow position={[0.08, 0.04, 0.05]} scale={0.55}>
        <dodecahedronGeometry args={[0.1, 0]} />
        <meshStandardMaterial color={palette.rock2} flatShading roughness={1} />
      </mesh>
    </group>
  );
}

function TinyHouse({ variant }: { variant: number }) {
  const palette = usePalette();
  const woodColor = palette.treeTrunk;
  const roofColor = palette.villageRoof;
  const wallColor = palette.villageWall;
  return (
    <group>
      {/* 屋体 — 使用场景色 */}
      <mesh castShadow position={[0, 0.1, 0]}>
        <boxGeometry args={[0.18, 0.2, 0.15]} />
        <meshStandardMaterial color={wallColor} roughness={0.85} />
      </mesh>
      {/* 横向木纹条 */}
      {[0.04, 0.1, 0.16].map((y) => (
        <mesh key={y} position={[0, y, 0.08]}>
          <boxGeometry args={[0.19, 0.02, 0.01]} />
          <meshStandardMaterial color={woodColor} roughness={0.9} />
        </mesh>
      ))}
      {/* 三角屋顶 — 深陶瓦色 */}
      <mesh castShadow position={[0, 0.23, 0]}>
        <coneGeometry args={[0.15, 0.12, 4]} />
        <meshStandardMaterial color={roofColor} flatShading roughness={0.95} />
      </mesh>
      {/* 小窗户 — 暖黄光 */}
      <mesh position={[0.06, 0.12, 0.08]}>
        <boxGeometry args={[0.03, 0.04, 0.01]} />
        <meshBasicMaterial color="#fdf6e3" />
      </mesh>
      {/* 门 */}
      <mesh position={[-0.04, 0.06, 0.08]}>
        <boxGeometry args={[0.035, 0.08, 0.01]} />
        <meshStandardMaterial color={woodColor} roughness={0.8} />
      </mesh>
      {/* 烟囱 */}
      <mesh position={[0.05, 0.28, -0.02]}>
        <boxGeometry args={[0.03, 0.08, 0.03]} />
        <meshStandardMaterial color={woodColor} roughness={0.9} />
      </mesh>
    </group>
  );
}

/** 水洼里的小睡莲（很小，不遮住连续水面） */
function PondLily({ variant }: { variant: number }) {
  const palette = usePalette();
  return (
    <group position={[0.05 - (variant % 3) * 0.05, 0.015, 0.04 - ((variant >> 1) % 3) * 0.04]}>
      <mesh position={[0, 0, 0]} scale={[1, 0.25, 1]}>
        <circleGeometry args={[0.035, 8]} />
        <meshStandardMaterial color={palette.mossTop} roughness={0.6} />
      </mesh>
      <mesh position={[0.012, 0.012, 0]}>
        <sphereGeometry args={[0.012, 6, 4]} />
        <meshStandardMaterial color={palette.pondFlower} emissive="#7a4058" emissiveIntensity={0.25} />
      </mesh>
    </group>
  );
}

function TileDecoration({
  tile,
  index,
  hasTree,
}: {
  tile: Tile;
  index: number;
  hasTree: boolean;
}) {
  const { kind } = tile;
  if (kind === "rock") return <TinyRock variant={index} />;
  if (kind === "water") {
    // 水塘本身已是刻进地形的蓝色水洼，只在水面点缀一朵睡莲
    if ((tile.x * 5 + tile.z * 13 + index) % 2 !== 0) return null;
    return <PondLily variant={index} />;
  }
  // 河流/瀑布已整片刻入地形连续水面，这里不需要额外贴片
  if (kind === "river" || kind === "waterfall") return null;
  if (kind === "village") return <TinyHouse variant={index} />;
  if (kind === "moss") {
    // 苔原：一部分长蕨，其余补矮草，不让地块空着
    if ((tile.x * 7 + tile.z * 11 + 30) % 3 !== 0) return <TinyFern variant={index} />;
    return <TinyTuft variant={index + tile.x * 3} />;
  }
  // forest：种树位内的长树，其余是带草簇/小石的草地（不再是空方块）
  if (!hasTree) return <TinyTuft variant={index} />;
  return <TinyTree variant={index} />;
}

// ============================================================
// ── 单个地块 ──
// ============================================================

// ── 单块地面装饰：树/草/房子站在“自己地块的连续地表高度”上，不悬空 ──
function DecorTile({
  tile,
  index,
  hasTree,
  isNewTree,
}: {
  tile: Tile;
  index: number;
  hasTree: boolean;
  isNewTree: boolean;
}) {
  const baseY = surfaceYOf(tile);
  return (
    <group position={[tile.x * UNIT, baseY, tile.z * UNIT]}>
      <TileDecoration tile={tile} index={index} hasTree={hasTree} />
      {isNewTree && (
        <group position={[0, 0.22, 0]}>
          <NewTileSparkle color="#fff9c4" />
        </group>
      )}
    </group>
  );
}

// ============================================================
// ── 主岛 ──
// ============================================================

function Island({
  unlockedCount,
  treeCount,
  todayCheckin,
  palette,
}: {
  unlockedCount: number;
  treeCount: number;
  todayCheckin: boolean;
  palette: ScenePalette;
}) {
  const island = useRef<Group>(null);
  const reducedMotion = useReducedMotion();

  useFrame((state) => {
    if (!island.current || reducedMotion) return;
    island.current.position.y = Math.sin(state.clock.elapsedTime * 0.55) * 0.025;
  });

  // 最新收获种下的那棵树 = 第 treeCount 棵（今天来看小岛时点亮星光）
  const hasPlantedToday = todayCheckin && treeCount > 0;

  // 当前“海岸”半径：打卡越多圆越大；圆沿平滑弧线切开地形，边缘永无尖刺
  const n = Math.min(unlockedCount, islandOrder.length);
  const rho = useMemo(() => rhoForUnlocked(n), [n]);

  // 整张连续地形网格（海岸半径或换场景配色时重建一次）
  const terrainGeo = useMemo(
    () => buildTerrainGeometry(rho, palette),
    [rho, palette]
  );

  return (
    <group ref={island} rotation={[0, -0.18, 0]}>
      {/* 连续地表：一整张带厚度的实心岛体（顶面 + 平滑弧线悬崖 + 封底） */}
      <mesh geometry={terrainGeo} receiveShadow castShadow>
        <meshStandardMaterial vertexColors roughness={0.95} side={DoubleSide} />
      </mesh>
      {/* 地表上的树/草丛/房子，脚踩连续地表高度 */}
      {islandOrder.slice(0, n).map((tile, index) => {
        const treeRank =
          tile.kind === "forest"
            ? (forestSlotOf.get(islandKey(tile)) ?? null)
            : null;
        const hasTree = treeRank !== null && treeRank <= treeCount;
        const isNewTree = hasTree && hasPlantedToday && treeRank === treeCount;
        return (
          <DecorTile
            key={islandKey(tile)}
            tile={tile}
            index={index}
            hasTree={hasTree}
            isNewTree={isNewTree}
          />
        );
      })}
    </group>
  );
}

function useReducedMotion() {
  return useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );
}

// ── 场景光：跟随 palette（雪/雨两套完全不同的环境色） ──
function SceneLights() {
  const palette = usePalette();
  return (
    <hemisphereLight args={[palette.sceneSky, palette.sceneGround, palette.sceneIntensity]} />
  );
}

// ============================================================
// ── 导出 ──
// ============================================================

type LearningIslandProps = {
  totalCheckins?: number;
  streak?: number;
  totalHours?: number;
  /** 今天是否已打卡（决定“最新一棵树”星光） */
  todayCheckin?: boolean;
  /** 岛上树的数量 = 盆栽成熟收获次数（不再是打卡数） */
  treeCount?: number;
};

export function LearningIsland({
  totalCheckins = 0,
  streak = 0,
  totalHours = 0,
  todayCheckin = false,
  treeCount = 0,
}: LearningIslandProps) {
  const unlockedCount = Math.min(totalTiles, INITIAL_TILES + totalCheckins * TILES_PER_CHECKIN);
  // 树 = 盆栽浇水成熟收获的次数（由花园系统驱动，见 plant-card）
  const treeCountFinal = Math.min(treeCount, forestSlots.length);

  // ── 场景 → PALETTE：自动跟随 html[data-scene] 切换 ──
  const [palette, setPalette] = useState<ScenePalette>(() => paletteForScene(readSceneFromDOM()));

  useEffect(() => {
    if (typeof document === "undefined") return;
    // 初始状态
    setPalette(paletteForScene(document.documentElement.dataset.scene));
    // 监听场景切换（用户在 selector 点雨林/雪景）
    const observer = new MutationObserver(() => {
      setPalette(paletteForScene(document.documentElement.dataset.scene));
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-scene"],
    });
    return () => observer.disconnect();
  }, []);

  return (
    <PaletteContext.Provider value={palette}>
      <div
        className="relative h-full w-full touch-none"
        role="img"
        aria-label={`小岛：种下了 ${treeCountFinal} 棵树，累计 ${totalCheckins} 天来打卡，连续 ${streak} 天，学习 ${Math.round(totalHours * 10) / 10} 小时`}
      >
        <Canvas
          dpr={[1, 1.65]}
          shadows
          orthographic
          camera={{ position: [8, 8, 9], zoom: 62, near: 0.1, far: 120 }}
          gl={{ antialias: true, alpha: true }}
        >
          <ambientLight intensity={1.4} />
          <SceneLights />
          <directionalLight
            castShadow
            position={[5, 10, 4]}
            intensity={2.0}
            color="#f0faf0"
            shadow-mapSize-width={1024}
            shadow-mapSize-height={1024}
            shadow-camera-left={-8}
            shadow-camera-right={8}
            shadow-camera-top={8}
            shadow-camera-bottom={-8}
          />
          <Island
            unlockedCount={unlockedCount}
            treeCount={treeCountFinal}
            todayCheckin={todayCheckin}
            palette={palette}
          />
          <ContactShadows
            position={[0, -1.2, 0]}
            opacity={0.35}
            scale={14}
            blur={2.8}
            far={6}
            color="#010906"
          />
          <OrbitControls
            makeDefault
            enablePan={false}
            enableZoom={false}
            minPolarAngle={Math.PI / 3.2}
            maxPolarAngle={Math.PI / 2.4}
            minAzimuthAngle={-Infinity}
            maxAzimuthAngle={Infinity}
            target={[0, 0.3, 0]}
          />
        </Canvas>
        <div className="pointer-events-none absolute bottom-4 right-4 flex items-center gap-2 text-xs text-white/45">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          拖动查看
        </div>
      </div>
    </PaletteContext.Provider>
  );
}
