import requests
import os

def test_backend_submission():
    url = "http://127.0.0.1:8000/submit"
    
    # Prepara dados fictícios
    data = {
        "razao_social_1": "Teste Empresa 1 LTDA",
        "razao_social_2": "Teste Empresa 2 LTDA",
        "razao_social_3": "Teste Empresa 3 LTDA",
        "nome_fantasia": "Tech Test",
        "cep": "01001-000",
        "rua": "Praça da Sé",
        "numero": "123",
        "bairro": "Sé",
        "cidade": "São Paulo",
        "uf": "SP",
        "inscricao_imobiliaria": "999888",
        "area_m2": "100",
        "tipo_imovel": "sala",
        "cnae_codigo": "6201-5/01",
        "cnae_descricao": "Desenvolvimento de programas de computador",
        "valor_capital": "10000",
        "tipo_integralizacao": "ato",
        "meio_integralizacao": "dinheiro",
        "email": "teste@empresa.com",
        "telefone": "(11) 99999-9999"
    }
    
    # Cria arquivos temporários para teste
    files = [
        ('files', ('doc1.png', b'dummy content', 'image/png')),
        ('files', ('doc2.pdf', b'dummy content', 'application/pdf')),
        ('files', ('doc3.jpg', b'dummy content', 'image/jpeg'))
    ]
    
    try:
        response = requests.post(url, data=data, files=files)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        assert response.status_code == 200
        assert "id" in response.json()
        print("Teste de Backend: SUCESSO")
    except Exception as e:
        print(f"Teste de Backend: FALHA - {e}")

if __name__ == "__main__":
    test_backend_submission()
