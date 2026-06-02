# 文件预览组件

## ImagePreview

简洁的图片预览组件，自动适配本地模式（Tauri/Local）和 Sandbox 模式。

### 特性

- ✅ 仅支持图片文件（png, jpg, jpeg, gif, webp）
- ✅ 自动检测文件类型
- ✅ Tauri 模式：直接读取本地文件
- ✅ Sandbox 模式：使用服务器 URL
- ✅ 加载状态和错误处理
- ✅ 响应式设计

### 使用示例

```tsx
import { ImagePreview } from '@/components/ui/file-preview';
import { File } from '@/store/chat/types';

function MessageBox({ files }: { files: File[] }) {
  return (
    <div>
      {files.map((file, index) => (
        <div key={index}>
          <span>{file.fileName}</span>
          <ImagePreview file={file} />
        </div>
      ))}
    </div>
  );
}
```

### 完整示例

```tsx
import { ImagePreview } from '@/components/ui/file-preview';

function FileList({ files }: { files: File[] }) {
  return (
    <div className="grid grid-cols-3 gap-4">
      {files.map((file, index) => (
        <div key={index} className="border rounded-lg p-4">
          <div className="mb-2">
            <p className="font-medium">{file.fileName}</p>
            <p className="text-sm text-muted-foreground">{file.fileExtension.toUpperCase()}</p>
          </div>
          <ImagePreview file={file} className="rounded-md" />
        </div>
      ))}
    </div>
  );
}
```

### Props

| 参数        | 类型     | 必填 | 默认值 | 说明           |
| ----------- | -------- | ---- | ------ | -------------- |
| `file`      | `File`   | ✅   | -      | 文件对象       |
| `className` | `string` | ❌   | `''`   | 自定义样式类名 |

### 行为说明

1. **非图片文件**：返回 `null`，不渲染任何内容
2. **加载中**：显示加载动画（Loader2）
3. **加载失败**：显示"图片加载失败"提示
4. **加载成功**：显示图片预览（最大高度 12rem）

### 支持的图片格式

- PNG (`.png`)
- JPEG (`.jpg`, `.jpeg`)
- GIF (`.gif`)
- WebP (`.webp`)

### 自动适配

```typescript
// Tauri 模式（本地文件）
{
  fileName: "photo.png",
  localPath: "/Users/alice/photo.png",
  fileType: "local_path"
}
// → 读取本地文件并转换为 Data URL

// Sandbox 模式（已上传）
{
  fileName: "photo.png",
  fileUrl: "https://example.com/files/photo.png",
  fileType: "uploaded"
}
// → 直接使用服务器 URL
```

### 性能优化

- `loading="lazy"`: 懒加载图片
- `max-h-48`: 限制最大高度，避免撑大容器
- `object-contain`: 保持图片比例
