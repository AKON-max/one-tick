"use server";

// ============================================================
// 设置 Server Action（薄封装）
// 业务逻辑由 FastAPI 提供：
//  - updateProfile  → PATCH /api/user/profile
//  - changePassword → POST /api/auth/change-password
// 调用方无需改动；改密成功后由前端清理 cookie 完成登出。
// ============================================================

import { apiFetch } from "@/lib/server-api";
import type { ActionResult } from "@/types";

export async function updateProfile(formData: FormData): Promise<ActionResult> {
  try {
    await apiFetch("/api/user/profile", {
      method: "PATCH",
      body: JSON.stringify({
        name: (formData.get("name") as string) || undefined,
        bio: (formData.get("bio") as string) || null,
      }),
    });
    return { success: true };
  } catch (error) {
    console.error("[updateProfile] 失败:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "更新资料失败，请稍后重试",
    };
  }
}

export async function changePassword(formData: FormData): Promise<ActionResult> {
  try {
    await apiFetch("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        currentPassword: formData.get("currentPassword") as string,
        newPassword: formData.get("newPassword") as string,
      }),
    });
    return { success: true };
  } catch (error) {
    console.error("[changePassword] 失败:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "修改密码失败，请稍后重试",
    };
  }
}
