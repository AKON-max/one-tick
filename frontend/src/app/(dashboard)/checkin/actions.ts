"use server";

// ============================================================
// 签到 Server Action（薄封装）
// 业务逻辑由 FastAPI 提供（POST /api/checkins/daily），
// 这里只负责转发请求 + 控制页面缓存失效，调用方无需改动。
// ============================================================

import { revalidatePath } from "next/cache";
import type { ActionResult } from "@/types";
import type { SceneType } from "@/lib/scene-meta";
import { apiFetch } from "@/lib/server-api";

export async function dailyCheckin(mood?: string, scene?: SceneType): Promise<ActionResult> {
  try {
    const res = await apiFetch<{ success: boolean }>("/api/checkins/daily", {
      method: "POST",
      body: JSON.stringify({ mood: mood ?? null, scene: scene ?? null }),
    });
    if (!res.success) return { success: false, error: "签到失败" };

    revalidatePath("/checkin");
    revalidatePath("/dashboard");
    revalidatePath("/statistics");
    return { success: true };
  } catch (error) {
    console.error("[dailyCheckin] 失败:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "签到失败",
    };
  }
}
