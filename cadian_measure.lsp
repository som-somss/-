; CADian 2023 실측 자동작성 - 테스트 버전
; 명령: MEASUREAUTO
; 동작:
; 1) CSV 선택
; 2) CSV 값 개수만큼 실측 위치를 순서대로 클릭
; 3) 각 클릭점에서 "실측값" 레이어의 가장 가까운 곡선을 기준선으로 자동 선택
; 4) 기준선에 직각이며 입력값을 전체 길이로 하는 LINE 생성
; 5) 생성된 LINE들의 양 끝점을 클릭 순서대로 연결(2END)
;
; 지원 기준객체: LINE, LWPOLYLINE, POLYLINE, ARC, SPLINE

(vl-load-com)

(defun MA:Split (s sep / p out)
  (setq out '())
  (while (setq p (vl-string-search sep s))
    (setq out (append out (list (substr s 1 p))))
    (setq s (substr s (+ p (strlen sep) 1)))
  )
  (append out (list s))
)

(defun MA:ReadCSV (fn / f line cols vals v)
  (setq vals '())
  (if (setq f (open fn "r"))
    (progn
      (while (setq line (read-line f))
        (setq cols (MA:Split line ","))
        (if (>= (length cols) 2)
          (progn
            (setq v (atof (vl-string-trim " " (cadr cols))))
            (if (> v 0.0)
              (setq vals (append vals (list v)))
            )
          )
        )
      )
      (close f)
    )
  )
  vals
)

(defun MA:CurveP (e / t)
  (setq t (cdr (assoc 0 (entget e))))
  (member t '("LINE" "LWPOLYLINE" "POLYLINE" "ARC" "SPLINE"))
)

(defun MA:GetLayerCurves (/ ss i e out)
  (setq out '())
  (if (setq ss (ssget "_X" '((8 . "실측값"))))
    (progn
      (setq i 0)
      (repeat (sslength ss)
        (setq e (ssname ss i))
        (if (MA:CurveP e)
          (setq out (cons e out))
        )
        (setq i (1+ i))
      )
    )
  )
  out
)

(defun MA:ClosestCurve (pt curves / e obj cp d best bestd)
  (setq best nil bestd nil)
  (foreach e curves
    (setq obj (vlax-ename->vla-object e))
    (setq cp
      (vl-catch-all-apply
        'vlax-curve-getClosestPointTo
        (list obj (trans pt 1 0))
      )
    )
    (if (not (vl-catch-all-error-p cp))
      (progn
        (setq d (distance (trans pt 1 0) cp))
        (if (or (null bestd) (< d bestd))
          (setq best e bestd d)
        )
      )
    )
  )
  best
)

(defun MA:MakeLine (p1 p2)
  (entmakex
    (list
      '(0 . "LINE")
      (cons 8 "실측값")
      (cons 10 p1)
      (cons 11 p2)
    )
  )
)

(defun MA:MakePline (pts / data)
  (if (> (length pts) 1)
    (progn
      (setq data
        (append
          (list
            '(0 . "LWPOLYLINE")
            '(100 . "AcDbEntity")
            (cons 8 "실측값")
            '(100 . "AcDbPolyline")
            (cons 90 (length pts))
            '(70 . 0)
          )
          (mapcar
            '(lambda (p)
               (cons 10 (list (car p) (cadr p)))
             )
            pts
          )
        )
      )
      (entmakex data)
    )
  )
)

(defun c:MEASUREAUTO
  (/ fn vals curves pts pt i len e obj cp param deriv ang half z
     p1 p2 sideA sideB topPts botPts)

  (vl-load-com)
  (prompt "\n[MEASUREAUTO] 실측값 자동작성 시작")

  ; CSV 선택
  (setq fn (getfiled "실측값 CSV 선택" "" "csv" 0))

  (if (null fn)
    (prompt "\n취소되었습니다.")
    (progn
      (setq vals (MA:ReadCSV fn))

      (cond
        ((< (length vals) 2)
          (prompt "\n오류: CSV에서 유효한 실측값을 2개 이상 읽지 못했습니다.")
        )

        ((null (tblsearch "LAYER" "실측값"))
          (prompt "\n오류: 현재 도면에 '실측값' 레이어가 없습니다.")
        )

        ((null (setq curves (MA:GetLayerCurves)))
          (prompt "\n오류: '실측값' 레이어에서 기준으로 사용할 LINE/PLINE/ARC/SPLINE을 찾지 못했습니다.")
        )

        (T
          (prompt
            (strcat
              "\n실측값 "
              (itoa (length vals))
              "개를 읽었습니다."
            )
          )
          (prompt "\n사진/현장자료의 순서와 동일하게 측점을 클릭하세요.")

          ; 값 개수만큼 포인트 입력
          (setq pts '() i 0)
          (while (< i (length vals))
            (setq pt
              (getpoint
                (strcat
                  "\n"
                  (itoa (1+ i))
                  "번 위치 (값 "
                  (rtos (nth i vals) 2 2)
                  ") 지정 <Enter=취소>: "
                )
              )
            )
            (if pt
              (progn
                (setq pts (append pts (list pt)))
                (setq i (1+ i))
              )
              (setq i (length vals) pts nil)
            )
          )

          (if pts
            (progn
              (setq topPts '() botPts '() i 0)

              (repeat (length vals)
                (setq pt  (nth i pts))
                (setq len (nth i vals))

                ; 클릭점에서 "실측값" 레이어의 가장 가까운 기준곡선 자동 선택
                (setq e (MA:ClosestCurve pt curves))

                (if e
                  (progn
                    (setq obj (vlax-ename->vla-object e))
                    (setq cp
                      (vlax-curve-getClosestPointTo
                        obj
                        (trans pt 1 0)
                      )
                    )
                    (setq param (vlax-curve-getParamAtPoint obj cp))
                    (setq deriv (vlax-curve-getFirstDeriv obj param))

                    ; 기준선 접선 + 90도
                    (setq ang
                      (+ (atan (cadr deriv) (car deriv))
                         (/ pi 2.0))
                    )
                    (setq half (/ len 2.0))
                    (setq z (if (caddr cp) (caddr cp) 0.0))

                    (setq p1
                      (list
                        (+ (car cp) (* half (cos ang)))
                        (+ (cadr cp) (* half (sin ang)))
                        z
                      )
                    )
                    (setq p2
                      (list
                        (- (car cp) (* half (cos ang)))
                        (- (cadr cp) (* half (sin ang)))
                        z
                      )
                    )

                    (MA:MakeLine p1 p2)

                    ; 2END용 양쪽 끝점.
                    ; 첫 선은 화면 Y로 방향을 정하고 이후에도 같은 법선 방향을 유지.
                    (if (> (cadr p1) (cadr p2))
                      (setq sideA p1 sideB p2)
                      (setq sideA p2 sideB p1)
                    )
                    (setq topPts (append topPts (list sideA)))
                    (setq botPts (append botPts (list sideB)))
                  )
                )
                (setq i (1+ i))
              )

              ; 2END 자동
              (MA:MakePline topPts)
              (MA:MakePline botPts)

              (prompt
                (strcat
                  "\n완료: 실측선 "
                  (itoa (length vals))
                  "개 + 양쪽 끝선 2개를 '실측값' 레이어에 생성했습니다."
                )
              )
            )
            (prompt "\n측점 지정이 취소되어 아무것도 생성하지 않았습니다.")
          )
        )
      )
    )
  )
  (princ)
)

(prompt "\nCADian 실측 자동작성 로드 완료. 명령어: MEASUREAUTO")
(princ)
