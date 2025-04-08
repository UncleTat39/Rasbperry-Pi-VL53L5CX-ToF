from vl53l5cx.vl53l5cx import VL53L5CX
import time
import RPi.GPIO as GPIO
import traceback
import numpy as np
import cv2

# GPIO 設置
LPN_PIN = 17  # GPIO 17

def create_distance_image(distances, width=8, height=8, max_distance=4000):
    """創建視覺化距離圖像"""
    if not distances or len(distances) != width * height:
        # 創建全黑圖像
        return np.zeros((height * 30, width * 30, 3), dtype=np.uint8)
    
    # 創建黑色背景圖像
    image = np.zeros((height * 30, width * 30, 3), dtype=np.uint8)
    
    try:
        # 遍歷所有距離值
        for y in range(height):
            for x in range(width):
                idx = y * width + x
                if idx >= len(distances):
                    continue  # 跳過超出範圍的索引
                
                distance = distances[idx]
                
                # 計算像素坐標
                pixel_x = x * 30
                pixel_y = y * 30
                
                # 如果距離有效，設置顏色
                if 0 < distance < max_distance:
                    # 距離映射到顏色 (近=紅色，遠=藍色)
                    normalized = min(1.0, distance / max_distance)
                    
                    # 使用熱度圖色彩(近=紅，遠=藍)
                    color = [0, 0, 0]  # BGR格式
                    
                    if normalized < 0.5:
                        # 紅色到黃色漸變
                        color[2] = 255  # 紅色分量最大
                        color[1] = int(255 * (normalized * 2))  # 綠色分量逐漸增加
                    else:
                        # 黃色到藍色漸變
                        color[2] = int(255 * (2 - normalized * 2))  # 紅色分量逐漸減少
                        color[1] = int(255 * (2 - normalized * 2))  # 綠色分量逐漸減少
                        color[0] = int(255 * (normalized * 2 - 1))  # 藍色分量逐漸增加
                    
                    # 繪製彩色矩形
                    cv2.rectangle(image, (pixel_x, pixel_y), (pixel_x + 29, pixel_y + 29), color, -1)
                    
                    # 在矩形中顯示距離值
                    if distance < 10000:  # 只顯示合理範圍內的距離
                        cv2.putText(image, f"{int(distance)}", 
                                  (pixel_x + 2, pixel_y + 20), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                else:
                    # 對於無效距離值，繪製灰色矩形
                    cv2.rectangle(image, (pixel_x, pixel_y), (pixel_x + 29, pixel_y + 29), (50, 50, 50), -1)
        
        # 繪製網格線
        for y in range(1, height):
            cv2.line(image, (0, y * 30), (width * 30, y * 30), (100, 100, 100), 1)
        
        for x in range(1, width):
            cv2.line(image, (x * 30, 0), (x * 30, height * 30), (100, 100, 100), 1)
    
    except Exception as e:
        # 在圖像上顯示錯誤信息
        cv2.putText(image, f"Error: {str(e)}", (10, image.shape[0] - 30), 
                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    
    return image

def run_improved_test():
    try:
        # 初始化 GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LPN_PIN, GPIO.OUT, initial=GPIO.HIGH)
        
        # 硬件復位
        print("執行硬件復位...")
        GPIO.output(LPN_PIN, GPIO.LOW)
        time.sleep(0.5)
        GPIO.output(LPN_PIN, GPIO.HIGH)
        time.sleep(1.0)
        
        # 創建傳感器
        print("創建傳感器實例...")
        tof = VL53L5CX()
        
        # 檢查活動狀態
        alive = tof.is_alive()
        print(f"傳感器活動狀態: {alive}")
        if not alive:
            print("錯誤: 傳感器不響應")
            return
        
        # 初始化
        print("初始化傳感器...")
        tof.init()
        
        # 設置參數
        print("設置參數...")
        tof.set_resolution(64)  # 8x8
        tof.set_ranging_frequency_hz(5)  # 5Hz
        
        # 嘗試其他設置
        try:
            print("設置電源模式...")
            tof.set_power_mode(1)  # 使用低功耗模式
        except Exception as e:
            print(f"設置電源模式失敗: {e}")
        
        # 啟動測量
        print("啟動測量...")
        tof.start_ranging()
        
        print("\n開始連續測量，按 'q' 停止，按 'r' 重置")
        print("-" * 50)
        
        count = 0
        error_count = 0
        start_time = time.time()
        last_print_time = time.time()
        last_reset_time = time.time()
        distances_history = []  # 保存最近的有效數據
        
        # 創建視窗顯示數據
        cv2.namedWindow("VL53L5CX ToF Sensor", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("VL53L5CX ToF Sensor", 400, 400)
        
        # 主循環
        running = True
        while running:
            try:
                current_time = time.time()
                
                # 檢查按鍵
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    running = False
                    break
                elif key == ord('r'):
                    print("\n用戶請求重置...")
                    # 重置傳感器
                    tof.stop_ranging()
                    time.sleep(0.5)
                    GPIO.output(LPN_PIN, GPIO.LOW)
                    time.sleep(0.5)
                    GPIO.output(LPN_PIN, GPIO.HIGH)
                    time.sleep(1.0)
                    tof.init()
                    tof.set_resolution(64)
                    tof.set_ranging_frequency_hz(5)
                    tof.start_ranging()
                    print("傳感器已重置")
                    last_reset_time = current_time
                
                # 檢查數據是否就緒
                ready = tof.check_data_ready()
                
                if ready:
                    # 獲取數據
                    try:
                        data = tof.get_ranging_data()
                        count += 1
                        
                        # 處理數據
                        if hasattr(data, 'distance_mm') and len(data.distance_mm) > 0:
                            distances = data.distance_mm
                            
                            # 保存有效數據
                            if len(distances) == 64:  # 確保是完整的8x8數據
                                distances_history = distances
                            
                            # 創建視覺化
                            image = create_distance_image(distances)
                            
                            # 添加文本
                            elapsed = current_time - start_time
                            rate = count / elapsed if elapsed > 0 else 0
                            status_text = f"讀取次數: {count} | 速率: {rate:.1f}/秒"
                            cv2.putText(image, status_text, (10, image.shape[0] - 10), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                            
                            # 添加錯誤計數
                            if error_count > 0:
                                error_text = f"錯誤次數: {error_count}"
                                cv2.putText(image, error_text, (10, 20), 
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                            
                            # 顯示圖像
                            cv2.imshow("VL53L5CX ToF Sensor", image)
                            
                            # 每隔一段時間打印狀態
                            if current_time - last_print_time >= 2.0:
                                last_print_time = current_time
                                
                                # 計算有效點數
                                valid_count = sum(1 for d in distances if d > 0 and d < 4000)
                                
                                print(f"\n讀取次數: {count} | 速率: {rate:.1f}/秒 | 錯誤: {error_count}")
                                print(f"有效距離點: {valid_count}/{len(distances)}")
                                
                                if valid_count > 0:
                                    valid_distances = [d for d in distances if d > 0 and d < 4000]
                                    print(f"距離範圍: {min(valid_distances):.0f} - {max(valid_distances):.0f} mm")
                    
                    except Exception as e:
                        error_count += 1
                        if error_count % 5 == 1:  # 限制錯誤輸出頻率
                            print(f"\n獲取或處理數據時出錯 ({error_count}): {e}")
                            
                            # 如果是索引錯誤，打印更多信息
                            if "index" in str(e).lower():
                                if hasattr(data, 'distance_mm'):
                                    print(f"距離數組長度: {len(data.distance_mm)}")
                        
                        # 如果有保存的歷史數據，顯示最後的有效數據
                        if distances_history:
                            image = create_distance_image(distances_history)
                            cv2.putText(image, f"使用歷史數據 - 錯誤: {e}", (10, image.shape[0] - 30), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
                            cv2.imshow("VL53L5CX ToF Sensor", image)
                
                # 檢查是否需要自動重置 (當長時間無數據或錯誤過多時)
                no_data_timeout = 10  # 無數據超時(秒)
                if (count > 0 and current_time - last_reset_time > no_data_timeout and 
                    (error_count > 20 or (current_time - last_print_time > no_data_timeout and ready == False))):
                    print("\n檢測到問題，執行自動重置...")
                    # 重置傳感器
                    try:
                        tof.stop_ranging()
                        time.sleep(0.5)
                        GPIO.output(LPN_PIN, GPIO.LOW)
                        time.sleep(0.5)
                        GPIO.output(LPN_PIN, GPIO.HIGH)
                        time.sleep(1.0)
                        tof.init()
                        tof.set_resolution(64)
                        tof.set_ranging_frequency_hz(5)
                        tof.start_ranging()
                        print("傳感器已自動重置")
                        last_reset_time = current_time
                        error_count = 0  # 重置錯誤計數
                    except Exception as e:
                        print(f"重置失敗: {e}")
                
                # 短暫休眠
                time.sleep(0.05)
            
            except Exception as e:
                error_count += 1
                print(f"\n主循環異常 ({error_count}): {e}")
                traceback.print_exc()
                time.sleep(1.0)  # 出錯後等待較長時間
    
    except KeyboardInterrupt:
        print("\n測試被用戶中斷")
    except Exception as e:
        print(f"\n測試出錯: {e}")
        traceback.print_exc()
    finally:
        # 停止測量和清理
        try:
            if 'tof' in locals():
                print("\n停止測量...")
                tof.stop_ranging()
        except Exception as e:
            print(f"停止測量時出錯: {e}")
        
        cv2.destroyAllWindows()
        GPIO.cleanup()
        print("測試結束")

if __name__ == "__main__":
    run_improved_test()
