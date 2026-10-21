/**
 * [POS] `/chat` 路径别名。避免被 `[chatId]` 动态段解析为 id=`chat` 从而在会话不存在时显示 404。
 */
import { redirect } from 'next/navigation';

export default function ChatPathAlias() {
  redirect('/');
}
