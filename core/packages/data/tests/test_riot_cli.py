"""CLI exercises a fixture at the external HTTP seam; no real account is queried."""

import json

from tft_data.cli import main


def test_riot_match_cli_routes_owner_only_and_keeps_key_out_of_output(tmp_path, capsys):
    from tft_data.riot import HTTPResponse, RiotClient

    requested = []

    def transport(url, headers):
        requested.append((url, headers))
        if "/by-riot-id/" in url:
            body = {"puuid": "fixture-owner"}
        elif "/entries/by-puuid/" in url:
            body = [
                {
                    "queueType": "RANKED_TFT",
                    "tier": "GOLD",
                    "rank": "II",
                    "leaguePoints": 20,
                }
            ]
        elif "/ids?" in url:
            body = ["FIXTURE_1"]
        else:
            body = {
                "metadata": {"participants": ["fixture-owner"]},
                "info": {
                    "queue_id": 1100,
                    "tft_set_number": 18,
                    "game_datetime": 1791244800000,
                    "participants": [
                        {
                            "puuid": "fixture-owner",
                            "placement": 3,
                            "units": [],
                            "traits": [],
                        }
                    ],
                },
            }
        return HTTPResponse(200, {}, body)

    key = tmp_path / "key"
    key.write_text("fixture-secret\n")
    client = RiotClient(key_path=key, transport=transport, sleep=lambda _: None)
    output = tmp_path / "own-matches.json"
    result = main(
        [
            "riot-matches",
            "--game-name",
            "Fixture",
            "--tag-line",
            "EU",
            "--set",
            "18",
            "--output",
            str(output),
        ],
        riot_client=client,
    )
    assert result == 0
    assert (
        json.loads(output.read_text())["matches"][0]["info"]["participants"][0][
            "placement"
        ]
        == 3
    )
    assert "fixture-secret" not in capsys.readouterr().out
    assert all(
        headers["User-Agent"].startswith("TFTAssistant/") for _, headers in requested
    )
    assert "europe.api.riotgames.com" in requested[0][0]
    assert "eun1.api.riotgames.com" in requested[1][0]
