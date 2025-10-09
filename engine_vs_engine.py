import pexpect, time, chess, datetime, chess.pgn
from typing import Dict, Any, Tuple

ENGINE_PATHS = {"Engine A": "", "Engine B": ""}
match_config = {}

def _parse_info(line: str, data: Dict[str, Any]):
    try:
        parts = line.split()
        d = dict(zip(parts[1::2], parts[2::2]))
        data['depth'] = int(d.get("depth", data['depth']))
        data['nodes'] = int(d.get("nodes", data['nodes']))
        if "score" in d:
            stype = d["score"]
            sval = int(d[stype])
            data['score_cp'] = sval / 100.0 if stype == "cp" else None
            data['score_mate'] = sval if stype == "mate" else None
    except: pass

def start_engine(path: str, name: str) -> pexpect.spawn:
    try:
        proc = pexpect.spawn(path, encoding='utf-8', timeout=None)
        proc.sendline("uci"); proc.expect("uciok", timeout=120)
        
        contempt_key = "contemptA" if name == "Engine A" else "contemptB"
        contempt = globals().get("match_config", {}).get(contempt_key)
        threads = globals().get("match_config", {}).get("threads", 1)
        hash_size = globals().get("match_config", {}).get("hash_size", 16)

        proc.sendline(f"setoption name Contempt value {contempt}")
        proc.sendline(f"setoption name Threads value {threads}")
        proc.sendline(f"setoption name Hash value {hash_size}")
                
        proc.sendline("isready"); proc.expect("readyok", timeout=120)
        return proc
    except Exception as e:
        raise Exception(f"ERRO ao iniciar '{name}': {e}")

def run_chess_match(e1_name: str, e1_path: str, e2_name: str, e2_path: str, config: Dict[str, Any]) -> str:
    global match_config
    match_config = config
    
    e1_proc, e2_proc = None, None
    board, pgn_moves, result = chess.Board(config.get('initial_fen', chess.STARTING_FEN)), [], "*"
    time_limit, increment = config.get('timelimit_ms', 600000), config.get('increment_ms', 100)
    time_left = {chess.WHITE: time_limit, chess.BLACK: time_limit}
    
    try:
        e1_proc = start_engine(e1_path, e1_name)
        e2_proc = start_engine(e2_path, e2_name)
        procs = {chess.WHITE: e1_proc, chess.BLACK: e2_proc}

        while not board.is_game_over():
            turn = board.turn
            current_proc = procs[turn]
            
            current_proc.sendline(f"position fen {board.fen()}")
            current_proc.sendline(f"go wtime {time_left[chess.WHITE]} btime {time_left[chess.BLACK]} winc {increment} binc {increment}")
            
            move_data = {'best_move': None, 'depth': None, 'nodes': None, 'score_cp': None, 'score_mate': None}
            start_time = time.monotonic()
            
            while True:
                line = current_proc.readline().strip()
                if not line: continue
                if "info" in line: _parse_info(line, move_data)
                elif line.startswith("bestmove"): move_data['best_move'] = line.split()[1]; break
            
            time_spent_ms = (time.monotonic() - start_time) * 1000
            time_left[turn] = max(0, time_left[turn] - time_spent_ms) + increment
            
            best_move_uci = move_data['best_move']
            if not best_move_uci or best_move_uci == "resign" or time_left[turn] <= 0:
                result = "0-1" if turn == chess.WHITE else "1-0"
                break

            try:
                move = chess.Move.from_uci(best_move_uci)
                if move not in board.legal_moves: raise ValueError
                move_san = board.san(move)
                board.push(move)
                pgn_moves.append(move_san)
            except:
                result = "0-1" if turn == chess.WHITE else "1-0"
                break
            
        if board.is_game_over() and result == "*": result = board.result()

        # Monta PGN e Cabeçalho
        game = chess.pgn.Game()
        game.headers["Event"] = config.get("event", "Engine Battle")
        game.headers["Site"] = config.get("site", "Local")
        game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        game.headers["White"] = e1_name
        game.headers["Black"] = e2_name
        game.headers["Result"] = result

        temp_board = chess.Board(config.get('initial_fen', chess.STARTING_FEN))
        node = game
        for move_san in pgn_moves:
            try:
                move = temp_board.parse_san(move_san)
                node = node.add_variation(move)
                temp_board.push(move)
            except: pass
        
        return str(game)
    
    except Exception as e:
        return f"[ERRO FATAL] {e}"
    finally:
        for proc in [e1_proc, e2_proc]:
            if proc and proc.isalive():
                try: proc.sendline("quit"); proc.close()
                except: pass

if __name__ == "__main__":
    match_config = {
        'hash_size': 2000,
        'threads': 1,
        'timelimit_ms': 100,
        'increment_ms': 500,
        'initial_fen': chess.STARTING_FEN,
        'contemptA': 0,
        'contemptB': 0,
        'event': "Battle",
        'site': "Machine"
    }

    final_pgn = run_chess_match(
        "Engine A", ENGINE_PATHS["Engine A"],
        "Engine B", ENGINE_PATHS["Engine B"],
        match_config
    )
    
    filename = "match.pgn"
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(final_pgn)
        print(f"\n===== PGN FINAL DA PARTIDA =====")
        print(f"O PGN foi salvo em: {os.path.abspath(filename)}")
    except Exception as e:
        print(f"\nERRO ao salvar o arquivo PGN: {e}")