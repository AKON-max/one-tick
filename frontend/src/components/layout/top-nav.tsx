"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { SquaresFour, ListChecks, BookOpen, Tree, ChartLine, Sparkle, Question, ArrowUpRight, X, List, Hourglass } from "@phosphor-icons/react";
import { LogoutButton } from "@/app/(dashboard)/actions";
import { AppAvatar } from "@/components/ui/app-avatar";
import { NotificationBell } from "./notification-bell";
import { AmbientSound } from "@/components/dashboard/ambient-sound";
import { ChatRoom } from "@/components/chatroom/chat-room";
import { useOnboarding } from "@/components/onboarding/onboarding-provider";

const navigation = [
  { href: "/dashboard", label: "今日", icon: SquaresFour },
  { href: "/plans", label: "学习计划", icon: ListChecks },
  { href: "/docs", label: "我的文档", icon: BookOpen },
  { href: "/checkin", label: "生长记录", icon: Tree },
  { href: "/statistics", label: "学习复盘", icon: ChartLine },
  { href: "/agent", label: "学习伙伴", icon: Sparkle },
];

export function TopNav({ user }: { user: { id: string; name: string; email: string; image?: string | null } }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [avatar, setAvatar] = useState(user.image ?? null);
  const { startTour } = useOnboarding();
  useEffect(() => {
    const update = (event: Event) => setAvatar((event as CustomEvent<string>).detail);
    window.addEventListener("avatar:changed", update);
    return () => window.removeEventListener("avatar:changed", update);
  }, []);
  const current = navigation.find((item) => pathname.startsWith(item.href));

  return <>
    <header className="workspace-topbar dashboard-nav">
      <button className="workspace-icon mobile-menu" aria-label={open ? "关闭导航" : "打开导航"} aria-expanded={open} aria-controls="workspace-navigation" onClick={() => setOpen(!open)}>{open ? <X /> : <List />}</button>
      <div className="workspace-breadcrumb"><span>我的学习空间</span><span>/</span><strong>{current?.label ?? "个人资料"}</strong></div>
      <div className="workspace-tools"><AmbientSound /><ChatRoom /><NotificationBell /></div>
    </header>
    {open && <button className="workspace-scrim" aria-label="关闭导航" onClick={() => setOpen(false)} />}
    <aside id="workspace-navigation" className={`workspace-sidebar ${open ? "is-open" : ""}`}>
      <Link href="/dashboard" className="workspace-brand" onClick={() => setOpen(false)}><span className="workspace-brand-mark"><Hourglass weight="fill" /></span><span>一刻<small>SUMMER CHECKIN</small></span></Link>
      <p className="workspace-nav-label">我的日常</p>
      <nav aria-label="主导航">{navigation.map(({ href, label, icon: Icon }) => {
        const active = pathname.startsWith(href);
        return <Link key={href} href={href} aria-current={active ? "page" : undefined} className={`workspace-nav-item ${active ? "is-active" : ""}`} onClick={() => setOpen(false)}><Icon weight={active ? "fill" : "regular"} /><span>{label}</span>{active && <span className="workspace-active-dot" />}</Link>;
      })}</nav>
      <div className="workspace-sidebar-footer">
        <Link href="/agent" className="workspace-companion"><Sparkle weight="duotone" /><span>把难题一起想清楚</span><ArrowUpRight /></Link>
        <button className="workspace-help" onClick={startTour}><Question />重新认识这里</button>
        <Link href="/profile" className="workspace-user"><AppAvatar image={avatar} name={user.name} size="sm" /><span><strong>{user.name}</strong><small>个人资料</small></span></Link>
        <LogoutButton />
      </div>
    </aside>
  </>;
}
