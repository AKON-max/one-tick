import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // 数据加载型 effect 的迁移是后续性能优化项；先保留为 warning，避免遮蔽真正的新错误。
      "react-hooks/set-state-in-effect": "warn",
      // 第三方可视化和 SDK 兼容代码中仍存在少量 any；逐步收敛，不阻断提交。
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
