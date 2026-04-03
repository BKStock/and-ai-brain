"""
&AI QUANTUM EDGE - 全自動動画制作システム
OpenClaw × Seedance 2 × FFmpeg

フロー:
1. KKがテーマをTelegramで投げる
2. ボンズが台本・ショットリストを生成
3. fal.ai/Seedance 2で動画素材を生成
4. FFmpegで自動編集・テロップ追加
5. TikTok/X/YouTube向けに書き出し
6. 完了通知をTelegramに送信
"""

import os, json, subprocess, requests, time
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv
load_dotenv('/Users/mr.k/Projects/and-ai-brain/.env')

BOT_TOKEN = os.environ.get("QE_REPORT_BOT_TOKEN")
CHAT_ID = os.environ.get("QE_OWNER_CHAT_ID", "5791086501")
FAL_KEY = "394ea344-58ac-4a34-93f1-c7ca11e3f711"
OUTPUT_DIR = os.path.expanduser("~/Projects/and-ai-brain/videos")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# SNS別設定
PLATFORM_CONFIGS = {
    "tiktok": {"size": "9:16", "width": 1080, "height": 1920, "duration": 30, "label": "TikTok"},
    "youtube": {"size": "16:9", "width": 1920, "height": 1080, "duration": 60, "label": "YouTube"},
    "x": {"size": "16:9", "width": 1280, "height": 720, "duration": 140, "label": "X(Twitter)"},
    "instagram": {"size": "9:16", "width": 1080, "height": 1920, "duration": 60, "label": "Instagram Reels"},
}


def send_telegram(msg: str, parse_mode="Markdown"):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": parse_mode},
        timeout=10
    )


def generate_script(theme: str, platform: str = "tiktok") -> dict:
    """
    Claude AIでテーマから台本・ショットリストを自動生成
    """
    config = PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS["tiktok"])
    client = Anthropic()
    
    prompt = f"""あなたは{config['label']}向けの投資・金融コンテンツクリエイターです。

テーマ: {theme}
プラットフォーム: {config['label']}
動画尺: 約{config['duration']}秒
アスペクト比: {config['size']}

以下の形式でJSON出力してください:

{{
  "title": "動画タイトル（30文字以内）",
  "hook": "最初の3秒のフック（視聴者を引き込む一言）",
  "script": [
    {{
      "scene": 1,
      "duration": 5,
      "narration": "ナレーションテキスト",
      "visual_prompt": "英語でSeedance 2へのビジュアルプロンプト（詳細に）",
      "caption": "テロップテキスト（日本語）"
    }}
  ],
  "cta": "CTA（行動喚起）テキスト",
  "hashtags": ["#タグ1", "#タグ2", "#タグ3"]
}}

シーンは4〜6個作成してください。
visual_promptは必ず英語で、カメラワーク・ライティング・雰囲気を詳細に記述してください。"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    import re
    text = response.content[0].text
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return None


def generate_video_clip(visual_prompt: str, duration: int, scene_num: int, project_id: str) -> str:
    """
    fal.ai / Seedance 2で動画クリップを生成
    """
    import fal_client
    
    os.environ["FAL_KEY"] = FAL_KEY
    
    print(f"    🎬 シーン{scene_num} 生成中...")
    
    try:
        # Seedance 2 (seedance-v1)
        result = fal_client.subscribe(
            "fal-ai/seedance-v1-lite",
            arguments={
                "prompt": visual_prompt,
                "duration": min(duration, 10),  # 最大10秒
                "aspect_ratio": "9:16",
            }
        )
        
        if result and result.get("video"):
            video_url = result["video"]["url"]
            output_path = f"{OUTPUT_DIR}/{project_id}_scene{scene_num:02d}.mp4"
            
            # 動画ダウンロード
            r = requests.get(video_url, timeout=60)
            with open(output_path, 'wb') as f:
                f.write(r.content)
            
            print(f"    ✅ シーン{scene_num} 完了: {output_path}")
            return output_path
    
    except Exception as e:
        print(f"    ❌ シーン{scene_num} エラー: {str(e)[:80]}")
        # フォールバック: 静止画から動画を生成
        return generate_placeholder_clip(visual_prompt, duration, scene_num, project_id)
    
    return None


def generate_placeholder_clip(prompt: str, duration: int, scene_num: int, project_id: str) -> str:
    """
    フォールバック: FFmpegでテキスト動画を生成
    """
    output_path = f"{OUTPUT_DIR}/{project_id}_scene{scene_num:02d}.mp4"
    
    # 背景色とテキストで仮の動画を生成
    colors = ["#1a1a2e", "#16213e", "#0f3460", "#533483", "#2d6a4f"]
    color = colors[scene_num % len(colors)]
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color={color}:size=1080x1920:duration={duration}:rate=30",
        "-vf", f"drawtext=text='{prompt[:50]}':fontcolor=white:fontsize=40:x=(w-tw)/2:y=(h-th)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    return output_path if result.returncode == 0 else None


def add_captions_and_music(clips: list, script: dict, project_id: str, platform: str) -> str:
    """
    FFmpegでクリップを結合し、テロップとBGMを追加
    """
    config = PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS["tiktok"])
    output_path = f"{OUTPUT_DIR}/{project_id}_final_{platform}.mp4"
    
    # クリップリストファイルを作成
    concat_file = f"{OUTPUT_DIR}/{project_id}_concat.txt"
    valid_clips = [c for c in clips if c and os.path.exists(c)]
    
    if not valid_clips:
        print("❌ 有効なクリップがありません")
        return None
    
    with open(concat_file, 'w') as f:
        for clip in valid_clips:
            f.write(f"file '{clip}'\n")
    
    # クリップを結合
    temp_output = f"{OUTPUT_DIR}/{project_id}_temp.mp4"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-c:v", "libx264", "-ccc", "yuv420p",
        temp_output
    ]
    subprocess.run(cmd_concat, capture_output=True, timeout=120)
    
    if not os.path.exists(temp_output):
        # シンプルコピー
        cmd_concat2 = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-c", "copy",
            temp_output
        ]
        subprocess.run(cmd_concat2, capture_output=True, timeout=120)
    
    # テロップを追加
    title = script.get('title', '&AI QUANTUM EDGE')
    cta = script.get('cta', '')
    
    filter_complex = (
        f"drawtext=text='{title[:30]}':fontcolor=white:fontsize=50:"
        f"x=(w-tw)/2:y=100:enable='between(t,0,3)',"
        f"drawtext=text='{cta[:30]}':fontcolor=yellow:fontsize=45:"
        f"x=(w-tw)/2:y=(h-150):enable='gte(t,{max(1, len(valid_clips)*3-3)})'"
    )
    
    cmd_final = [
        "ffmpeg", "-y",
        "-i", temp_output if os.path.exists(temp_output) else valid_clips[0],
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-s", f"{config['width']}x{config['height']}",
        output_path
    ]
    
    result = subprocess.run(cmd_final, capture_output=True, timeout=120)
    
    # クリーンアップ
    if os.path.exists(concat_file):
        os.remove(concat_file)
    if os.path.exists(temp_output):
        os.remove(temp_output)
    
    if result.returncode == 0 and os.path.exists(output_path):
        return output_path
    
    # フォールバック: そのまま返す
    return valid_clips[0] if valid_clips else None


def create_video(theme: str, platforms: list = ["tiktok"]) -> dict:
    """
    メイン実行関数: テーマ→完成動画
    """
    project_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {}
    
    send_telegram(f"""🎬 *動画制作開始！*
━━━━━━━━━━━━━━━

📝 テーマ: {theme}
📱 配信先: {', '.join([PLATFORM_CONFIGS[p]['label'] for p in platforms if p in PLATFORM_CONFIGS])}
🆔 Project: {project_id}

制作中... しばらくお待ちください ⏳""")
    
    # 台本生成
    print("📝 台本生成中...")
    script = generate_script(theme, platforms[0])
    
    if not script:
        send_telegram("❌ 台本生成に失敗しました")
        return {}
    
    scenes = script.get("script", [])
    print(f"  ✅ {len(scenes)}シーンの台本生成完了")
    
    # 動画クリップ生成
    print("\n🎬 動画クリップ生成中...")
    clips = []
    for i, scene in enumerate(scenes):
        clip_path = generate_video_clip(
            scene.get("visual_prompt", scene.get("narration", "")),
            scene.get("duration", 5),
            i + 1,
            project_id
        )
        if clip_path:
            clips.append(clip_path)
        time.sleep(2)  # レート制限
    
    print(f"\n  ✅ {len(clips)}/{len(scenes)}クリップ生成完了")
    
    # 各プラットフォーム向けに編集・書き出し
    for platform in platforms:
        if platform not in PLATFORM_CONFIGS:
            continue
        
        config = PLATFORM_CONFIGS[platform]
        print(f"\n✂️ {config['label']}向け編集中...")
        
        final_path = add_captions_and_music(clips, script, project_id, platform)
        
        if final_path and os.path.exists(final_path):
            results[platform] = final_path
            size_mb = os.path.getsize(final_path) / 1024 / 1024
            print(f"  ✅ {config['label']}: {final_path} ({size_mb:.1f}MB)")
    
    # 完了通知
    completed = [PLATFORM_CONFIGS[p]['label'] for p in results]
    
    msg = f"""✅ *動画制作完了！*
━━━━━━━━━━━━━━━

📝 タイトル: {script.get('title', theme)}
🎬 完成: {len(results)}本

"""
    
    for platform, path in results.items():
        size_mb = os.path.getsize(path) / 1024 / 1024
        msg += f"✅ {PLATFORM_CONFIGS[platform]['label']}: {size_mb:.1f}MB\n"
    
    msg += f"\n📋 台本:\n_{script.get('hook', '')}..._\n\n"
    msg += f"#️⃣ {' '.join(script.get('hashtags', [])[:5])}\n\n"
    msg += f"🦴 &AI QUANTUM EDGE Video Factory"
    
    send_telegram(msg)
    
    # 台本をファイルに保存
    script_path = f"{OUTPUT_DIR}/{project_id}_script.json"
    with open(script_path, 'w', encoding='utf-8') as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    
    return {
        "project_id": project_id,
        "script": script,
        "videos": results,
        "script_file": script_path
    }


def quick_test(theme: str = "&AI QUANTUM EDGEが月利5%を達成！AIが自動で投資する時代"):
    """クイックテスト（台本生成のみ）"""
    print(f"🎬 動画制作テスト\nテーマ: {theme}\n")
    
    print("📝 台本生成中...")
    script = generate_script(theme, "tiktok")
    
    if script:
        print(f"\n✅ 台本生成成功！")
        print(f"タイトル: {script.get('title', '')}")
        print(f"フック: {script.get('hook', '')}")
        print(f"シーン数: {len(script.get('script', []))}")
        print(f"ハッシュタグ: {' '.join(script.get('hashtags', []))}")
        print("\nシーン詳細:")
        for scene in script.get('script', [])[:3]:
            print(f"  Scene {scene['scene']}: {scene.get('narration', '')[:50]}...")
            print(f"    Caption: {scene.get('caption', '')}")
    
    return script


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        theme = " ".join(sys.argv[1:])
        result = create_video(theme, ["tiktok", "x"])
    else:
        # テスト実行
        quick_test()
