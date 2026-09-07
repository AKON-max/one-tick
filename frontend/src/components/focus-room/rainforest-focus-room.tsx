"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, ArrowsOut, ArrowsIn, BookOpen, Sparkle, Tree } from "@phosphor-icons/react";
import { PomodoroStation } from "./pomodoro-station";
import { LocalTodoPanel } from "./local-todo-panel";
import { PlantCard } from "../garden/plant-card";
import { useScene } from "@/context/scene-context";

export function RainforestFocusRoom() {
  const [immersive, setImmersive] = useState(false);
  const [date] = useState(() => new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "long" }).format(new Date()));
  const { scene, setScene } = useScene();
  useEffect(() => {
    document.body.classList.toggle("rainforest-immersive", immersive);
    const exit = (event: KeyboardEvent) => { if (event.key === "Escape") setImmersive(false); };
    window.addEventListener("keydown", exit);
    return () => { document.body.classList.remove("rainforest-immersive"); window.removeEventListener("keydown", exit); };
  }, [immersive]);

  return <div className="daily-workspace">
    <header className="daily-heading product-header">
      <div><p className="daily-date">{date || "新的一天"}</p><h1>今天，慢慢来。</h1><p>把心思放在眼前这一件事上。</p></div>
      <Link href="/plans" className="workspace-text-link">查看学习计划 <ArrowUpRight /></Link>
    </header>
    <div className="daily-grid">
      <div className="daily-task-column"><LocalTodoPanel />
        <div className="daily-shortcuts">
          <Link href="/docs"><BookOpen weight="duotone" /><span><strong>接着读，接着想</strong><small>回到我的文档</small></span><ArrowUpRight /></Link>
          <Link href="/agent"><Sparkle weight="duotone" /><span><strong>卡住了？一起想想</strong><small>与学习伙伴聊一聊</small></span><ArrowUpRight /></Link>
        </div>
      </div>
      <div className="daily-focus-column">
        <section className={`focus-desk ${immersive ? "is-immersive" : ""}`} aria-label="专注计时" data-tour="focus-immersive">
          <header><span className="focus-status"><i />留给自己的一刻</span><button className="workspace-icon" title={immersive ? "回到工作台" : "进入沉浸"} aria-label={immersive ? "回到工作台" : "进入沉浸"} onClick={() => setImmersive(!immersive)}>{immersive ? <ArrowsIn /> : <ArrowsOut />}</button></header>
          <PomodoroStation immersive={immersive} onStart={() => setImmersive(true)} />
          <div className="focus-scene-switch" aria-label="专注场景">{([{ id: "rain", name: "听雨" }, { id: "snow", name: "看雪" }, { id: "cloud", name: "望云" }] as const).map(item => <button key={item.id} aria-pressed={scene === item.id} onClick={() => setScene(item.id)}>{item.name}</button>)}</div>
        </section>
        <div className="daily-growth-heading"><Tree weight="duotone" /><h2>一点点，长成一片</h2><Link href="/checkin" title="查看我的小岛" aria-label="查看我的小岛"><ArrowUpRight /></Link></div>
        <PlantCard />
      </div>
    </div>
    <footer className="daily-footer"><span>按自己的节奏，积累自己的答案。</span><Link href="/statistics">回看我的进步 <ArrowUpRight /></Link></footer>
  </div>;
}
