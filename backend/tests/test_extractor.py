import pytest

from app.extractor.domeggook import (
    DomeggookParseError,
    extract_product_no_from_url,
    normalize_domeggook_url,
    parse_price_tiers,
    parse_product_html,
)


SAMPLE_HTML = """
<!doctype html>
<html>
<head>
  <title>[도매꾹] 국산 튼튼한 스테인리스 집게 - 도매꾹</title>
  <meta property="og:title" content="[도매꾹] 국산 튼튼한 스테인리스 집게" />
  <meta property="og:image" content="https://cdn.example.com/upload/item/54804743/og_thumb.jpg" />
</head>
<body>
  <h1>국산 튼튼한 스테인리스 집게</h1>
  <div class="seller">판매자명 : 행복상사</div>
  <div>상품번호 : 54804743</div>
  <div class="category">주방용품 &gt; 조리도구 &gt; 집게</div>
  <img id="lThumbImg" src="//cdn.example.com/upload/item/54804743/thumb_main.jpg" />
  <table class="price">
    <tr><th>수량(개)</th><td>1~</td><td>1,000~</td><td>10,000~</td></tr>
    <tr><th>단가(원)</th><td>5,900</td><td>5,800</td><td>5,700</td></tr>
  </table>
  <div>최소구매수량 : 10개</div>
  <div>재고수량 : 123개</div>
  <div>원산지 : 대한민국</div>
  <div class="shipping">배송비 3,000원 / CJ대한통운 / 묶음배송 가능</div>
  <select name="option"><option>색상: 실버</option><option>색상: 블랙</option></select>
  <div>상세설명 이미지 사용여부 사용허용</div>
  <div id="detail">
    <img src="https://cdn.example.com/upload/item/54804743/54804743_stt_001.jpg" />
    <img src="https://cdn.example.com/upload/item/54804743/detail_002.jpg" />
    <img src="https://cdn.example.com/common/banner.jpg" />
    <img src="https://cdn.example.com/upload/item/54804743/54804743_stt_001.jpg" />
  </div>
</body>
</html>
"""


def test_normalize_url_and_product_no():
    url = normalize_domeggook_url("domeggook.com/54804743?foo=bar")
    assert url == "https://domeggook.com/54804743"
    assert extract_product_no_from_url(url) == "54804743"


@pytest.mark.parametrize("bad_url", ["https://example.com/54804743", "not a url", "https://domeggook.com/"])
def test_normalize_rejects_invalid_url(bad_url):
    with pytest.raises(DomeggookParseError):
        normalize_domeggook_url(bad_url)


def test_parse_price_tiers_from_table_like_text():
    text = "수량(개) 1~ 1,000~ 10,000~ 단가(원) 5,900 5,800 5,700"
    assert parse_price_tiers(text) == [
        {"min_qty": 1, "unit_price": 5900},
        {"min_qty": 1000, "unit_price": 5800},
        {"min_qty": 10000, "unit_price": 5700},
    ]


def test_parse_live_like_domeggook_price_table_ignores_total_quantity_noise():
    html = """
    <html><head><meta property="og:title" content="[도매꾹] 라이브형 상품" /></head><body>
      <div id="itemView">
        <div>총 수량 0 개 적용단가 원 &gt;</div>
        <table id="lBaseAmtTbl">
          <thead><tr><th>수량</th><td>단가</td></tr></thead>
          <tbody>
            <tr data-idx="1"><th>1 ~</th><td>5,900</td></tr>
            <tr data-idx="2"><th>1,000 ~</th><td>5,800</td></tr>
            <tr data-idx="3"><th>10,000 ~</th><td>5,700</td></tr>
          </tbody>
        </table>
        <div>상품번호 : 54804743</div>
      </div>
    </body></html>
    """

    product = parse_product_html(html, "https://domeggook.com/54804743")

    assert [(tier.min_qty, tier.unit_price) for tier in product.price_tiers] == [
        (1, 5900),
        (1000, 5800),
        (10000, 5700),
    ]


def test_parse_live_like_js_state_price_and_selectors_when_price_table_hidden():
    html = """
    <html><head><meta property="og:title" content="[도매꾹] 스킨포유 센텔라 시카 토너" /></head><body>
      <div id="itemView">
        <li class="dropdown nosub" id="lPathCat1"><a href="/main/">도매꾹홈</a></li>
        <li class="dropdown nosub" id="lPathCat2">화장품</li>
        <li class="dropdown nosub" id="lPathCat3">스킨케어</li>
        <li class="dropdown nosub" id="lPathCat4">스킨/토너</li>
        <div>상품번호 : 35444818</div>
        <script>
          window.lItem = {};
          window.lItem.store = { state: { baseAmtDome : 6500, baseAmtDomeIdx : 1 } };
        </script>
        <table id="lInfoBody">
          <tr class="lInfoDeli"><th>배송정보</th><td class="lInfoItemContent">택배 3,000원 / 주문시결제 묶음배송 가능</td></tr>
          <tr class="lInfoQty"><th>재고수량</th><td class="lInfoItemContent">982개</td></tr>
          <tr class="lInfoItemCountry"><th>원산지</th><td class="lInfoItemCountryContent">국산</td></tr>
        </table>
      </div>
    </body></html>
    """

    product = parse_product_html(html, "https://domeggook.com/35444818")

    assert product.price_tiers[0].min_qty == 1
    assert product.price_tiers[0].unit_price == 6500
    assert product.stock_qty == 982
    assert product.origin == "국산"
    assert "택배 3,000원" in product.shipping_summary
    assert "가격 구간을 찾지 못했습니다." not in product.warnings


def test_parse_live_like_domeggook_breadcrumb_uses_selected_path_only():
    html = """
      <div id="itemView">
        <li class="dropdown nosub" id="lPathCat1"><a href="/main/">도매꾹홈</a></li>
        <li class="dropdown nosub" id="lPathCat2">생활용품</li>
        <li class="dropdown" id="lPathCat3"><a href="/main/item/itemList.php?ca=12_08_00_00_00">주방용품</a><ol class="sub"><li><a>청소용품</a></li></ol></li>
        <li class="dropdown" id="lPathCat4"><a href="/main/item/itemList.php?ca=12_08_07_00_00">잔/컵</a><ol class="sub"><li><a>머그</a></li></ol></li>
        <li class="dropdown" id="lPathCat5"><a href="/main/item/itemList.php?ca=12_08_07_08_00">텀블러</a><ol class="sub"><li><a>스텐컵</a></li></ol></li>
        <div>상품번호 : 54804743</div>
      </div>
    </body></html>
    """

    product = parse_product_html(html, "https://domeggook.com/54804743")

    assert product.category_path == ["생활용품", "주방용품", "잔/컵", "텀블러"]


def test_parse_sample_html_extracts_mvp_fields():
    product = parse_product_html(SAMPLE_HTML, "https://domeggook.com/54804743")
    assert product.product_no == "54804743"
    assert product.original_name == "국산 튼튼한 스테인리스 집게"
    assert product.seller_name == "행복상사"
    assert product.category_path == ["주방용품", "조리도구", "집게"]
    assert product.price_tiers[0].min_qty == 1
    assert product.price_tiers[0].unit_price == 5900
    assert product.min_order_qty == 10
    assert product.stock_qty == 123
    assert product.origin == "대한민국"
    assert "배송비 3,000원" in product.shipping_summary
    assert "색상: 실버" in product.options
    assert product.thumbnail_url == "https://cdn.example.com/upload/item/54804743/thumb_main.jpg"
    assert product.detail_image_use_allowed is True
    assert product.detail_image_urls == [
        "https://cdn.example.com/upload/item/54804743/54804743_stt_001.jpg",
        "https://cdn.example.com/upload/item/54804743/detail_002.jpg",
    ]
    assert product.warnings == []


def test_parse_live_like_detail_html_preserves_contents_buffer_layout_and_urls():
    html = """
    <html><head><meta property="og:title" content="[도매꾹] 상세 원문 상품" /></head><body>
      <div>상품번호 : 35444818</div>
      <div id="lInfoViewItemContents" class="lInfoViewItemContents">
        <textarea id="contentsBuffer" style="display:none"><div style="text-align:center">
          <iframe src="https://www.youtube.com/embed/example" width="560" height="315"></iframe>
          <img src="//image.msscdn.net/images/detail-a.jpg" />
          <a href="/35444818">상품 링크</a>
        </div></textarea>
        <script>document.getElementById("lInfoViewItemContents").innerHTML = document.getElementById("contentsBuffer").value;</script>
      </div>
    </body></html>
    """

    product = parse_product_html(html, "https://domeggook.com/35444818")

    assert product.detail_html is not None
    assert "youtube.com/embed/example" in product.detail_html
    assert 'src="https://image.msscdn.net/images/detail-a.jpg"' in product.detail_html
    assert 'href="https://domeggook.com/35444818"' in product.detail_html


def test_parse_detail_images_prefers_detail_container_over_recommendations():
    html = SAMPLE_HTML.replace(
        "<div id=\"detail\">",
        '<div class="recommend-products"><img src="https://cdn.example.com/upload/item/99999999/detail_related.jpg" /></div><div id="detail">',
    )
    product = parse_product_html(html, "https://domeggook.com/54804743")

    assert product.detail_image_urls == [
        "https://cdn.example.com/upload/item/54804743/54804743_stt_001.jpg",
        "https://cdn.example.com/upload/item/54804743/detail_002.jpg",
    ]


def test_parse_external_editor_detail_images_from_live_detail_container():
    html = """
    <html><head><meta property="og:title" content="[도매꾹] 외부 상세 이미지 상품" /></head><body>
      <div>상품번호 : 65197944</div>
      <img id="lThumbImg" src="https://cdn1.domeggook.com/upload/item/2026/05/21/abc/abc_img_760.jpg" />
      <div id="lInfoViewItemContents" class="lInfoViewItemContents">
        <img src="https://superwhale.co.kr/web/upload/NNEditor/20260521/detail-shirt.jpg" />
        <center><img src="https://ai.esmplus.com/kbslco/kbt_notice.jpg" /></center>
      </div>
    </body></html>
    """

    product = parse_product_html(html, "https://domeggook.com/65197944")

    assert product.detail_image_urls == ["https://superwhale.co.kr/web/upload/NNEditor/20260521/detail-shirt.jpg"]


def test_parse_detail_container_skips_supplier_recommendation_block_but_keeps_real_images():
    html = """
    <html><head><meta property="og:title" content="[도매꾹] 텀블러" /></head><body>
      <div>상품번호 : 54804743</div>
      <img id="lThumbImg" src="https://cdn1.domeggook.com/upload/item/2025/02/27/abc/abc_img_760.jpg" />
      <div id="lInfoViewItemContents" class="lInfoViewItemContents">
        <div class="tmpl04">
          <a href="/59842602"><img src="https://cdn1.domeggook.com/upload/item/other/other_stt_330.png" /></a>
          <a href="/54804743"><img src="https://cdn1.domeggook.com/upload/item/2025/02/27/abc/abc_stt_330.png" /></a>
        </div>
        <textarea id="contentsBuffer">
          <div><img src="https://gi.esmplus.com/skdhwnd7/11/11.jpg" /></div>
          <div><img src="https://gi.esmplus.com/skdhwnd7/tumbler/222.jpg" /></div>
          <div><img src="https://cdn1.domeggook.com/image/mobile_v2/image/item/view/arrowDownGray.png" /></div>
        </textarea>
      </div>
    </body></html>
    """

    product = parse_product_html(html, "https://domeggook.com/54804743")

    assert product.detail_image_urls == [
        "https://gi.esmplus.com/skdhwnd7/11/11.jpg",
        "https://gi.esmplus.com/skdhwnd7/tumbler/222.jpg",
    ]
