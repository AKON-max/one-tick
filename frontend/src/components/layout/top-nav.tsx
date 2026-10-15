"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LogoutButton } from "@/app/(dashboard)/actions";
import {
  CaretDown,
  ChartLine,
  Check,
  House,
  ListChecks,
  List,
  Note,
  Question,
  Sparkle,
  X,
  Leaf,
  Tree,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { AppAvatar } from "@/components/ui/app-avatar";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { NotificationBell } from "@/components/layout/notification-bell";
import { AmbientSound } from "@/components/dashboard/ambient-sound";
import { ChatRoom } from "@/components/chatroom/chat-room";
import { SCENE_COPY, useScene, useSceneCopy, type SceneType } from "@/context/scene-context";
import { useOnboarding } from "@/components/onboarding/onboarding-provider";

interface TopNavProps {
  user: {
    id: string;
    name: string;
    email: string;
    image?: string | null;
  };
}

// 次要导航：场景无关的固定文字
const STATIC_FULL_NAV = [
  { href: "/checkin", label: "小岛", icon: Tree },
  { href: "/plans", label: "计划", icon: ListChecks },
  { href: "/docs", label: "阅读", icon: Note },
  { href: "/statistics", label: "主页", icon: ChartLine },
] as const;

// 三个场景：标签取 SCENE_COPY，缩略图与 landing / 小岛的场景选择器同一套素材
const SCENE_OPTIONS: { value: SceneType; label: string; image: string }[] = [
  { value: "rain", label: SCENE_COPY.rain.labelLong, image: "/rain.webp" },
  { value: "snow", label: SCENE_COPY.snow.labelLong, image: "/snow.webp" },
  { value: "cloud", label: SCENE_COPY.cloud.labelLong, image: "/cloud.webp" },
];

export function TopNav({ user }: TopNavProps) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [avatarId, setAvatarId] = useState(user.image ?? null);
  // 头像更新事件（profile 页换头像后派发）：右上角头像立即同步，不依赖 layout 刷新时机
  useEffect(() => {
    function onAvatarChanged(e: Event) {
      const detail = (e as CustomEvent<string>).detail;
      if (detail) setAvatarId(detail);
    }
    window.addEventListener("avatar:changed", onAvatarChanged);
    return () => window.removeEventListener("avatar:changed", onAvatarChanged);
  }, []);
  const router = useRouter();
  const { labelShort } = useSceneCopy();
  const { scene, setScene } = useScene();
  const { startTour } = useOnboarding();

  // 主要导航（顶部居中显示）：第一项按场景动态，其余静态
  const fullNav = [
    { href: "/dashboard", label: labelShort, icon: House },
    ...STATIC_FULL_NAV,
  ];

  const isActive = (href: string) =>
    pathname === href || (href !== "/dashboard" && pathname.startsWith(href));

  return (
    <>
      <header className="dashboard-nav pointer-events-none sticky top-0 z-40 w-full text-white">
        <div className="dashboard-nav__inner mx-auto flex h-20 max-w-[1440px] items-center justify-between gap-4 px-4 md:px-8">
          <Link href="/dashboard" className="pointer-events-auto flex items-center gap-2 rounded-full border border-white/12 bg-[var(--surface-nav-bg)] p-1.5 pr-3 text-xs font-semibold shadow-xl backdrop-blur-2xl lg:hidden"><span className="flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground"><Leaf className="size-3.5" weight="fill" /></span>One-Tick 一刻</Link>
          <div className="atomic-nav pointer-events-auto hidden items-center lg:flex">
            <Link href="/dashboard" className="atomic-nav__brand flex shrink-0 items-center gap-2.5">
              <span className="flex size-8 items-center justify-center rounded-full bg-primary text-primary-foreground"><Leaf className="size-4" weight="fill" /></span>
              <span className="whitespace-nowrap text-sm font-semibold">One-Tick 一刻</span>
            </Link>
            <nav className="atomic-nav__links" aria-label="主导航">
              {/* 第一项就是场景入口：点开可直接切 雨林 / 雪日 / 暖云（以前只有小岛页能切）。
                  原来这一项是可点的 /dashboard 链接，所以菜单里保留「进入自习室」，别把跳转弄丢 */}
              <DropdownMenu>
                <DropdownMenuTrigger
                  aria-label="切换学习场景"
                  className={cn(
                    "flex items-center rounded-full px-3 py-2 text-xs font-medium whitespace-nowrap outline-none transition-colors",
                    isActive("/dashboard") ? "bg-primary text-primary-foreground" : "text-white/52 hover:bg-white/8 hover:text-white"
                  )}
                >
                  <House className="size-4 shrink-0" weight={isActive("/dashboard") ? "fill" : "duotone"} />
                  <span className="atomic-nav__link-label">{labelShort}</span>
                  <CaretDown className="ml-1 size-3 shrink-0 opacity-60" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-52 rounded-xl border border-white/10 bg-background/98 p-1 shadow-2xl backdrop-blur-2xl">
                  <DropdownMenuItem
                    onClick={() => router.push("/dashboard")}
                    className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-4 py-2 text-sm text-white/75 transition-colors focus:bg-white/6 hover:bg-white/6 focus:text-white hover:text-white"
                  >
                    <House weight="fill" className="size-4 text-primary" />
                    进入自习室
                  </DropdownMenuItem>
                  <div className="h-px bg-white/5 mx-2 my-1" />
                  <div className="px-3 pb-1 pt-1.5 text-[11px] font-medium text-white/35">切换场景</div>
                  {SCENE_OPTIONS.map((s) => (
                    <DropdownMenuItem
                      key={s.value}
                      onClick={() => setScene(s.value)}
                      className={cn(
                        "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-4 py-2 text-sm transition-colors focus:bg-white/6 hover:bg-white/6",
                        scene === s.value ? "text-primary" : "text-white/75 focus:text-white hover:text-white"
                      )}
                    >
                      <span
                        className="size-5 shrink-0 rounded-md bg-cover bg-center ring-1 ring-white/15"
                        style={{ backgroundImage: `url(${s.image})` }}
                      />
                      <span className="flex-1">{s.label}</span>
                      {scene === s.value && <Check className="size-3.5 shrink-0" weight="bold" />}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
              {STATIC_FULL_NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center rounded-full px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors",
                    isActive(item.href) ? "bg-primary text-primary-foreground" : "text-white/52 hover:bg-white/8 hover:text-white"
                  )}
                >
                  <item.icon className="size-4 shrink-0" weight={isActive(item.href) ? "fill" : "duotone"} />
                  <span className="atomic-nav__link-label">{item.label}</span>
                </Link>
              ))}
            </nav>
            {/* 雨宝入口：与右侧悬浮球同一个目的地；标签常显，让 AI 入口在导航栏里一眼可见 */}
            <Link
              href="/agent"
              aria-label="问问雨宝"
              data-tour="ai-nav-entry"
              className="ml-2 flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-primary/30 bg-primary/12 px-3 text-xs font-semibold text-primary transition-all hover:border-primary/50 hover:bg-primary/20 active:scale-95"
            >
              <Sparkle className="size-3.5 shrink-0" weight="fill" />
              <span className="whitespace-nowrap">问问雨宝</span>
            </Link>
          </div>

          {/* 右侧：通知 + 用户菜单（桌面） */}
          <div className="dashboard-nav__tools pointer-events-auto hidden items-center gap-1 rounded-full border border-white/12 bg-[var(--surface-nav-bg)] p-1.5 shadow-xl backdrop-blur-2xl lg:flex">
            <AmbientSound />
            <ChatRoom />
            <NotificationBell />
            <DropdownMenu>
              <DropdownMenuTrigger aria-label="打开用户菜单" className="flex items-center gap-2 rounded-full bg-white/7 p-1 backdrop-blur-sm transition-all hover:bg-white/12">
                <AppAvatar image={avatarId} name={user.name ?? "U"} size="sm" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 rounded-xl border border-white/10 bg-background/98 p-1 shadow-2xl backdrop-blur-2xl">
                <div className="flex items-center gap-3 px-3 py-3">
                  <AppAvatar image={avatarId} name={user.name ?? "U"} size="md" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{user.name ?? "用户"}</p>
                    <p className="text-[11px] text-white/35 truncate">{user.email ?? ""}</p>
                  </div>
                </div>
                <div className="h-px bg-white/5 mx-2" />
                <DropdownMenuItem
                  onClick={startTour}
                  className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-4 py-2 text-sm text-white/75 transition-colors focus:bg-white/6 hover:bg-white/6 focus:text-white hover:text-white"
                >
                  <Question weight="fill" className="size-4 text-primary" />
                  新手引导
                </DropdownMenuItem>
                <div className="h-px bg-white/5 mx-2" />
                <LogoutButton />
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* 移动端：汉堡菜单 */}
          <div className="pointer-events-auto lg:hidden">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger className="flex items-center gap-2 rounded-md border border-white/25 bg-white/10 p-1.5 pr-3 text-white">
                <List className="h-4 w-4" />
                <AppAvatar image={avatarId} name={user.name ?? "U"} size="sm" />
              </SheetTrigger>
              <SheetContent side="right" className="w-72 p-0">
                <div className="flex h-16 items-center justify-between border-b border-border px-4">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground font-bold text-xs">
                      SC
                    </div>
                    <span className="font-semibold text-sm">菜单</span>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => setOpen(false)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <nav className="grid gap-1 p-3">
                  {fullNav.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setOpen(false)}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                        isActive(item.href)
                          ? "bg-accent text-accent-foreground"
                          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                      )}
                    >
                      <item.icon
                        weight={isActive(item.href) ? "fill" : "regular"}
                        className="h-5 w-5"
                      />
                      {item.label}
                    </Link>
                  ))}
                </nav>
                {/* 移动端同样要能切场景：顶栏的导航项在手机上收进了抽屉，
                    没有这一块的话，切场景仍然只能跑去小岛页 */}
                <div className="px-3 pb-2">
                  <p className="px-1 pb-2 text-[11px] font-medium text-muted-foreground">切换场景</p>
                  <div className="grid grid-cols-3 gap-1.5">
                    {SCENE_OPTIONS.map((s) => (
                      <button
                        key={s.value}
                        type="button"
                        onClick={() => {
                          setScene(s.value);
                          setOpen(false);
                        }}
                        className={cn(
                          "flex items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-xs font-medium transition-colors",
                          scene === s.value
                            ? "border-primary/40 bg-primary/12 text-primary"
                            : "border-border text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                        )}
                      >
                        <span
                          className="size-4 shrink-0 rounded bg-cover bg-center"
                          style={{ backgroundImage: `url(${s.image})` }}
                        />
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="absolute bottom-4 left-0 right-0 px-4">
                  <div className="flex flex-col gap-3 rounded-lg border border-border p-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {user.name ?? "用户"}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        {user.email ?? ""}
                      </p>
                    </div>
                    <LogoutButton />
                  </div>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>
    </>
  );
}
