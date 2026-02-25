#!/usr/bin/env python3
import sys
import argparse
import pandas as pd
from pathlib import Path

def assign_matching_type(w_class: str, wo_class: str) -> str:
    """
    w(With Context)와 w/o(Without Context)의 BG/SG 분류 결과를 기반으로
    매칭 유형(Type A, B, C, D)을 할당합니다.
    """
    if w_class == "BG" and wo_class == "BG":
        return "Type A"
    elif w_class == "BG" and wo_class == "SG":
        return "Type B"
    elif w_class == "SG" and wo_class == "BG":
        return "Type C"
    elif w_class == "SG" and wo_class == "SG":
        return "Type D"
    return "Unknown"

def get_type_description(type_code: str) -> str:
    if type_code == "Type A": return "Type A (w.BG - w/o.BG)"
    if type_code == "Type B": return "Type B (w.BG - w/o.SG)"
    if type_code == "Type C": return "Type C (w.SG - w/o.BG)"
    if type_code == "Type D": return "Type D (w.SG - w/o.SG)"
    return type_code

def process_file(input_path: Path):
    if not input_path.exists():
        print(f"Error: 파일 '{input_path}'을 찾을 수 없습니다.")
        sys.exit(1)
        
    print(f"Loading '{input_path}'...")
    df = pd.read_excel(input_path)
    
    required_cols = [
        "[WC/VAC] Classification", 
        "[WC/VAR] Classification", 
        "[WOC/VAC] Classification", 
        "[WOC/VAR] Classification"
    ]
    
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        print(f"Warning: 다음 필요한 컬럼이 없어 분류가 정확하지 않을 수 있습니다 -> {missing_cols}")
    
    print("Auto-assigning types based on 2x2 matrix for VA_C and VA_R...")
    
    df["VA_C Matching Type"] = df.apply(lambda row: get_type_description(assign_matching_type(
        row.get("[WC/VAC] Classification", ""), 
        row.get("[WOC/VAC] Classification", "")
    )), axis=1)
    
    df["VA_R Matching Type"] = df.apply(lambda row: get_type_description(assign_matching_type(
        row.get("[WC/VAR] Classification", ""), 
        row.get("[WOC/VAR] Classification", "")
    )), axis=1)
    
    df["Human Type Override (VA_C)"] = ""
    df["Human Type Override (VA_R)"] = ""
    df["Review Note"] = ""
    
    # 제거할 기존 컬럼 (만약 있다면)
    old_cols = ["Auto Type", "Human Type Override"]
    
    # 컬럼 순서 재배치 (보기 편하게 앞쪽으로 이동)
    cols = list(df.columns)
    new_cols = cols[:5] + [
        "VA_C Matching Type", 
        "VA_R Matching Type", 
        "Human Type Override (VA_C)", 
        "Human Type Override (VA_R)", 
        "Review Note"
    ] + [c for c in cols[5:] if c not in [
        "VA_C Matching Type", "VA_R Matching Type", 
        "Human Type Override (VA_C)", "Human Type Override (VA_R)", 
        "Review Note"
    ] + old_cols]
    
    df = df[new_cols]
    
    out_path = input_path.parent / f"{input_path.stem}_matched{input_path.suffix}"
    df.to_excel(out_path, index=False)
    print(f"\n=========================================")
    print(f"✅ 결과물이 성공적으로 저장되었습니다:\n-> '{out_path}'")
    print(f"   (VA_C와 VA_R 각각의 매칭 유형이 Type A~D로 분류되었습니다.)")
    print(f"=========================================\n")
    return out_path

def main():
    parser = argparse.ArgumentParser(description="Assign Interaction Types based on 2x2 matrix for VA_C and VA_R.")
    parser.add_argument("input_file", type=str, help="Path to 3_interaction_history.xlsx")
    args = parser.parse_args()
    
    process_file(Path(args.input_file))

if __name__ == "__main__":
    main()
