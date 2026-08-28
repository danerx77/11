"""
legal_titles_excel.py – Silnik eksportu do MS Excel poprzez interfejs COM
"""
import os
from pathlib import Path

class LegalTitlesExcelExporter:
    @staticmethod
    def export_format_1(tmpl_path: str, out_path: str, data_1a: list, data_1b: list, cols_1a: int, table_1a, table_1b):
        import win32com.client
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        try:
            wb = excel.Workbooks.Open(os.path.abspath(tmpl_path))
            ws = wb.ActiveSheet

            def merge_common_lp(start, count, cols_to_merge):
                if count <= 1: return
                groups = []
                curr_start = start
                curr_lp = str(ws.Cells(start, 1).Value)
                for r in range(start + 1, start + count):
                    lp = str(ws.Cells(r, 1).Value)
                    if lp != curr_lp:
                        groups.append((curr_start, r - 1))
                        curr_start = r
                        curr_lp = lp
                groups.append((curr_start, start + count - 1))

                for (g_start, g_end) in groups:
                    if g_start == g_end: continue
                    for c in cols_to_merge:
                        c_start = g_start
                        c_val = str(ws.Cells(g_start, c).Value).strip()
                        for r in range(g_start + 1, g_end + 1):
                            val = str(ws.Cells(r, c).Value).strip()
                            if val != c_val:
                                if r - 1 > c_start: ws.Range(ws.Cells(c_start, c), ws.Cells(r - 1, c)).Merge()
                                c_start = r
                                c_val = val
                        if g_end > c_start: ws.Range(ws.Cells(c_start, c), ws.Cells(g_end, c)).Merge()

            def apply_gui_spans(start, count, gui_table):
                if count <= 1: return
                col_mapping = [0, 2, 1, 3, 4, 5, 6, 7, 8]
                covered = set()
                for r_idx in range(count):
                    for c_idx in range(gui_table.columnCount()):
                        if (r_idx, c_idx) in covered: continue
                        row_span = gui_table.rowSpan(r_idx, c_idx)
                        col_span = gui_table.columnSpan(r_idx, c_idx)
                        if row_span > 1 or col_span > 1:
                            try:
                                excel_c1 = col_mapping.index(c_idx) + 1
                                excel_c2 = col_mapping.index(c_idx + col_span - 1) + 1
                            except ValueError: continue

                            if excel_c1 > excel_c2: excel_c1, excel_c2 = excel_c2, excel_c1
                            excel_r1 = start + r_idx
                            excel_r2 = start + r_idx + row_span - 1

                            rng = ws.Range(ws.Cells(excel_r1, excel_c1), ws.Cells(excel_r2, excel_c2))
                            rng.UnMerge()
                            rng.Merge()
                            for rr in range(row_span):
                                for cc in range(col_span): covered.add((r_idx + rr, c_idx + cc))

            start_row_1a = 0
            for r in range(1, 100):
                row_text = " ".join([str(ws.Cells(r, c).Value or '') for c in range(1, 10)]).lower()
                if 'przyłączanych' in row_text or 'przylaczanych' in row_text:
                    for r2 in range(r, r + 10):
                        if str(ws.Cells(r2, 1).Value or '').strip().lower() in ['lp', 'lp.', 'l.p.', 'nr']:
                            start_row_1a = r2 + 1
                            break
                    break

            if start_row_1a > 0 and len(data_1a) > 0:
                if len(data_1a) > 1:
                    ws.Rows(start_row_1a).Copy()
                    ws.Range(ws.Rows(start_row_1a + 1), ws.Rows(start_row_1a + len(data_1a) - 1)).Insert(Shift=-4121)
                    excel.Application.CutCopyMode = False

                for r_idx, row_data in enumerate(data_1a):
                    ws.Rows(start_row_1a + r_idx).Hidden = False
                    for c_idx, val in enumerate(row_data):
                        try:
                            cell = ws.Cells(start_row_1a + r_idx, c_idx + 1)
                            if c_idx == 0: cell.NumberFormat = "@"
                            cell.Value = str(val)
                        except: pass

                merge_common_lp(start_row_1a, len(data_1a), [1, 2, 7, 8, 9])
                apply_gui_spans(start_row_1a, len(data_1a), table_1a)
                rng = ws.Range(ws.Cells(start_row_1a, 1), ws.Cells(start_row_1a + len(data_1a) - 1, cols_1a))
                rng.Borders.LineStyle = 1
                rng.HorizontalAlignment = -4108
                rng.VerticalAlignment = -4108
                rng.WrapText = True
                rng.Font.Bold = False

            start_row_1b = 0
            search_start = start_row_1a + len(data_1a) if start_row_1a > 0 else 1
            for r in range(search_start, search_start + 200):
                row_text = " ".join([str(ws.Cells(r, c).Value or '') for c in range(1, 10)]).lower()
                if 'pozostałych' in row_text or 'pozostalych' in row_text:
                    for r2 in range(r, r + 10):
                        if str(ws.Cells(r2, 1).Value or '').strip().lower() in ['lp', 'lp.', 'l.p.', 'nr']:
                            start_row_1b = r2 + 1
                            break
                    break

            if start_row_1b > 0 and len(data_1b) > 0:
                if len(data_1b) > 1:
                    ws.Rows(start_row_1b).Copy()
                    ws.Range(ws.Rows(start_row_1b + 1), ws.Rows(start_row_1b + len(data_1b) - 1)).Insert(Shift=-4121)
                    excel.Application.CutCopyMode = False

                for r_idx, row_data in enumerate(data_1b):
                    ws.Rows(start_row_1b + r_idx).Hidden = False
                    for c_idx, val in enumerate(row_data):
                        try:
                            cell = ws.Cells(start_row_1b + r_idx, c_idx + 1)
                            if c_idx == 0: cell.NumberFormat = "@"
                            cell.Value = str(val)
                        except: pass

                merge_common_lp(start_row_1b, len(data_1b), [1, 2, 7, 8, 9])
                apply_gui_spans(start_row_1b, len(data_1b), table_1b)
                rng = ws.Range(ws.Cells(start_row_1b, 1), ws.Cells(start_row_1b + len(data_1b) - 1, 9))
                rng.Borders.LineStyle = 1
                rng.HorizontalAlignment = -4108
                rng.VerticalAlignment = -4108
                rng.WrapText = True
                rng.Font.Bold = False

            ext = Path(out_path).suffix.lower()
            file_format = 52 if ext == '.xlsm' else 51
            wb.SaveAs(os.path.abspath(out_path), FileFormat=file_format)
            wb.Close(SaveChanges=False)
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            try: excel.Quit()
            except: pass

    @staticmethod
    def export_format_2(tmpl_path: str, out_path: str, data_matrix: list, col_count: int, gui_table):
        import win32com.client
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        try:
            wb = excel.Workbooks.Open(os.path.abspath(tmpl_path))
            ws = wb.ActiveSheet

            start_row = 2
            for r in range(1, 15):
                val = str(ws.Cells(r, 1).Value or '').strip().lower()
                if val in ['lp', 'lp.', 'l.p.', 'nr', 'nr działki']:
                    start_row = r + 1
                    break

            if len(data_matrix) > 0:
                if len(data_matrix) > 1:
                    ws.Rows(start_row).Copy()
                    ws.Range(ws.Rows(start_row + 1), ws.Rows(start_row + len(data_matrix) - 1)).Insert(Shift=-4121)
                    excel.Application.CutCopyMode = False

                for r_idx, row_data in enumerate(data_matrix):
                    ws.Rows(start_row + r_idx).Hidden = False
                    for c_idx, val in enumerate(row_data):
                        try:
                            cell = ws.Cells(start_row + r_idx, c_idx + 1)
                            if c_idx == 0: cell.NumberFormat = "@"
                            cell.Value = str(val)
                        except: pass

                def apply_gui_spans(start, count, table_widget):
                    if count <= 1: return
                    covered = set()
                    for r_idx in range(count):
                        for c_idx in range(table_widget.columnCount()):
                            if (r_idx, c_idx) in covered: continue
                            row_span = table_widget.rowSpan(r_idx, c_idx)
                            col_span = table_widget.columnSpan(r_idx, c_idx)
                            if row_span > 1 or col_span > 1:
                                excel_r1 = start + r_idx
                                excel_c1 = c_idx + 1
                                excel_r2 = start + r_idx + row_span - 1
                                excel_c2 = c_idx + col_span
                                rng = ws.Range(ws.Cells(excel_r1, excel_c1), ws.Cells(excel_r2, excel_c2))
                                rng.UnMerge()
                                rng.Merge()
                                for rr in range(row_span):
                                    for cc in range(col_span): covered.add((r_idx + rr, c_idx + cc))

                apply_gui_spans(start_row, len(data_matrix), gui_table)
                rng = ws.Range(ws.Cells(start_row, 1), ws.Cells(start_row + len(data_matrix) - 1, col_count))
                rng.Borders.LineStyle = 1
                rng.HorizontalAlignment = -4108
                rng.VerticalAlignment = -4108
                rng.WrapText = True
                rng.Font.Bold = False

            ext = Path(out_path).suffix.lower()
            file_format = 52 if ext == '.xlsm' else 51
            wb.SaveAs(os.path.abspath(out_path), FileFormat=file_format)
            wb.Close(SaveChanges=False)
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            try: excel.Quit()
            except: pass

    @staticmethod
    def export_format_3(tmpl_path: str, out_path: str, data_matrix: list, t4_data: dict, gui_table):
        import win32com.client
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False

        try:
            wb = excel.Workbooks.Open(os.path.abspath(tmpl_path))
            ws = wb.ActiveSheet

            tab_val = t4_data.get('tabela', '').strip()
            if tab_val.upper().startswith('TABELA:'): tab_val = tab_val[7:].strip()
            if not tab_val: tab_val = "Tytuły prawne do nieruchomości"
            tab_val = "TABELA: " + tab_val

            nr_obi_val = t4_data.get('nr_obi', '').strip()
            t4_text = (f"{tab_val}               TEMAT: {t4_data['temat']}\n"
                       f"                    NR OBI: {nr_obi_val}           PROJEKTANT: {t4_data['projektant']}                         "
                       f"LOKALIZACJA: {t4_data['lokalizacja']}                                      INWESTOR: {t4_data['inwestor']}        ")
            ws.Cells(2, 1).Value = t4_text

            start_row = 5
            ws.Range(ws.Cells(start_row, 1), ws.Cells(1000, 17)).ClearContents()
            ws.Range(ws.Cells(start_row, 1), ws.Cells(1000, 17)).Borders.LineStyle = -4142

            if len(data_matrix) > 0:
                if len(data_matrix) > 1:
                    ws.Rows(start_row).Copy()
                    ws.Range(ws.Rows(start_row + 1), ws.Rows(start_row + len(data_matrix) - 1)).Insert(Shift=-4121)
                    excel.Application.CutCopyMode = False

                for r_idx, row_data in enumerate(data_matrix):
                    ws.Rows(start_row + r_idx).Hidden = False
                    for c_idx, val in enumerate(row_data):
                        try:
                            cell = ws.Cells(start_row + r_idx, c_idx + 1)
                            if c_idx == 0: cell.NumberFormat = "@"
                            cell.Value = str(val)
                        except: pass

                def merge_common_lp(start, count, cols_to_merge):
                    if count <= 1: return
                    groups = []
                    curr_start = start
                    curr_lp = str(ws.Cells(start, 1).Value)
                    for r in range(start + 1, start + count):
                        lp = str(ws.Cells(r, 1).Value)
                        if lp != curr_lp:
                            groups.append((curr_start, r - 1))
                            curr_start = r
                            curr_lp = lp
                    groups.append((curr_start, start + count - 1))

                    for (g_start, g_end) in groups:
                        if g_start == g_end: continue
                        for c in cols_to_merge:
                            c_start = g_start
                            c_val = str(ws.Cells(g_start, c).Value).strip()
                            for r in range(g_start + 1, g_end + 1):
                                val = str(ws.Cells(r, c).Value).strip()
                                if val != c_val:
                                    if r - 1 > c_start: ws.Range(ws.Cells(c_start, c), ws.Cells(r - 1, c)).Merge()
                                    c_start = r
                                    c_val = val
                            if g_end > c_start: ws.Range(ws.Cells(c_start, c), ws.Cells(g_end, c)).Merge()

                def apply_gui_spans(start, count, table_widget):
                    if count <= 1: return
                    covered = set()
                    for r_idx in range(count):
                        for c_idx in range(table_widget.columnCount()):
                            if (r_idx, c_idx) in covered: continue
                            row_span = table_widget.rowSpan(r_idx, c_idx)
                            col_span = table_widget.columnSpan(r_idx, c_idx)
                            if row_span > 1 or col_span > 1:
                                excel_r1 = start + r_idx
                                excel_c1 = c_idx + 1
                                excel_r2 = start + r_idx + row_span - 1
                                excel_c2 = c_idx + col_span
                                rng = ws.Range(ws.Cells(excel_r1, excel_c1), ws.Cells(excel_r2, excel_c2))
                                rng.UnMerge()
                                rng.Merge()
                                for rr in range(row_span):
                                    for cc in range(col_span): covered.add((r_idx + rr, c_idx + cc))

                merge_common_lp(start_row, len(data_matrix), [1, 2, 3, 4, 5, 6, 7, 8, 9, 17])
                apply_gui_spans(start_row, len(data_matrix), gui_table)
                rng = ws.Range(ws.Cells(start_row, 1), ws.Cells(start_row + len(data_matrix) - 1, 17))
                rng.Borders.LineStyle = 1
                rng.HorizontalAlignment = -4108
                rng.VerticalAlignment = -4108
                rng.WrapText = True
                rng.Font.Bold = False

            ext = Path(out_path).suffix.lower()
            file_format = 52 if ext == '.xlsm' else 51
            wb.SaveAs(os.path.abspath(out_path), FileFormat=file_format)
            wb.Close(SaveChanges=False)
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            try: excel.Quit()
            except: pass