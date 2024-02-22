import streamlit as st
import tensorflow as tf
from tensorflow.keras import layers
from tensorflow.keras.preprocessing.sequence import pad_sequences
import pickle
import numpy as np
import pandas as pd
import openpyxl
from io import BytesIO

# Definisi lapisan kustom dengan dekorator untuk serialisasi
@tf.keras.utils.register_keras_serializable()
class TransformerBlock(layers.Layer):
    def __init__(self, embed_dim, num_heads, ff_dim, rate=0.1, **kwargs):
        super(TransformerBlock, self).__init__(**kwargs)
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.ff_dim = ff_dim
        self.rate = rate
        self.att = layers.MultiHeadAttention(num_heads=num_heads, key_dim=embed_dim)
        self.ffn = tf.keras.Sequential([
            layers.Dense(ff_dim, activation="relu"), 
            layers.Dense(embed_dim)
        ])
        self.layernorm1 = layers.LayerNormalization(epsilon=1e-6)
        self.layernorm2 = layers.LayerNormalization(epsilon=1e-6)
        self.dropout1 = layers.Dropout(rate)
        self.dropout2 = layers.Dropout(rate)

    def call(self, inputs, training=False):
        attn_output = self.att(inputs, inputs)
        attn_output = self.dropout1(attn_output, training=training)
        out1 = self.layernorm1(inputs + attn_output)
        ffn_output = self.ffn(out1)
        ffn_output = self.dropout2(ffn_output, training=training)
        return self.layernorm2(out1 + ffn_output)

    def get_config(self):
        config = super(TransformerBlock, self).get_config()
        config.update({
            'embed_dim': self.embed_dim,
            'num_heads': self.num_heads,
            'ff_dim': self.ff_dim,
            'rate': self.rate
        })
        return config

@tf.keras.utils.register_keras_serializable()
class TokenAndPositionEmbedding(layers.Layer):
    def __init__(self, maxlen, vocab_size, embed_dim, **kwargs):
        super(TokenAndPositionEmbedding, self).__init__(**kwargs)
        self.maxlen = maxlen
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        self.token_emb = layers.Embedding(input_dim=vocab_size, output_dim=embed_dim)
        self.pos_emb = layers.Embedding(input_dim=maxlen, output_dim=embed_dim)

    def call(self, x):
        maxlen = tf.shape(x)[-1]
        positions = tf.range(start=0, limit=maxlen, delta=1)
        positions = self.pos_emb(positions)
        x = self.token_emb(x)
        return x + positions

    def get_config(self):
        config = super(TokenAndPositionEmbedding, self).get_config()
        config.update({
            'maxlen': self.maxlen,
            'vocab_size': self.vocab_size,
            'embed_dim': self.embed_dim
        })
        return config

# Fungsi untuk memuat model dengan lapisan kustom
def load_model(model_path):
    custom_objects = {
        "TokenAndPositionEmbedding": TokenAndPositionEmbedding,
        "TransformerBlock": TransformerBlock
    }
    return tf.keras.models.load_model(model_path, custom_objects=custom_objects)

# Function to load tokenizer and label encoder with st.cache_data
@st.cache_data
def load_support_files(tokenizer_path, label_encoder_path):
    with open(tokenizer_path, 'rb') as handle:
        tokenizer = pickle.load(handle)
    with open(label_encoder_path, 'rb') as file:
        label_encoder = pickle.load(file)
    return tokenizer, label_encoder

# Fungsi prediksi emosi
def predict_emotion(text, model, tokenizer, label_encoder):
    sequence = tokenizer.texts_to_sequences([text])
    padded_sequence = pad_sequences(sequence, maxlen=40)
    prediction = model.predict(padded_sequence)
    label_index = np.argmax(prediction, axis=1)[0]
    label = label_encoder.inverse_transform([label_index])
    return label[0]

def predict_bulk(model, tokenizer, label_encoder, data):
    sequences = tokenizer.texts_to_sequences(data['Review'].tolist())  # Pastikan ini sesuai dengan nama kolom teks Anda
    padded_sequences = pad_sequences(sequences, maxlen=40)
    predictions = model.predict(padded_sequences)
    prediction_indices = np.argmax(predictions, axis=1)
    prediction_labels = label_encoder.inverse_transform(prediction_indices)  # Mengubah indeks numerik menjadi label kelas
    return prediction_labels

# Fungsi untuk mengkonversi DataFrame ke CSV
def convert_df_to_csv(df):
    return df.to_csv().encode('utf-8')

def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return output.read()

def read_data(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    elif uploaded_file.name.endswith('.xlsx'):
        return pd.read_excel(uploaded_file)
    else:
        st.error("This file format is not supported! Please upload a CSV or Excel file.")
        return None
    
def create_sample_file(file_format):
    sample_data = {'Review': ['Saya sangat senang dengan layanannya', 'Produk ini sangat mengecewakan', 'Pengiriman cepat, terima kasih!']}
    df_sample = pd.DataFrame(sample_data)

    if file_format == 'csv':
        return df_sample.to_csv(index=False).encode('utf-8')
    elif file_format == 'excel':
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_sample.to_excel(writer, index=False)
        output.seek(0)
        return output.getvalue()

# Memuat model dan file pendukung
model = load_model('transformer_emotion.keras')
tokenizer, label_encoder = load_support_files('tokenizer.pickle', 'label_encoder.pickle')

# Menambahkan tab
tab1, tab2 = st.tabs(["Single Prediction", "Bulk Prediction"])

with tab1:
    # Kode untuk single prediction
    st.title('Prediksi Emosi dari Teks Review')
    user_input = st.text_area("Masukkan teks review di sini:")
    if st.button('Prediksi'):
        if user_input:
            predicted_emotion = predict_emotion(user_input, model, tokenizer, label_encoder)
            st.write(f'Emosi yang diprediksi: **{predicted_emotion}**')  # Pastikan ini dieksekusi dengan benar
        else:
            st.write('Silakan masukkan teks untuk prediksi.')

with tab2:
    st.write("Upload a CSV or Excel file for multi predictions.")
    
    with st.container():
        col1, col2 = st.columns([1, 2.7])
        with col1:
            # Tombol untuk mendownload CSV contoh
            st.download_button(
                label="Download Sample CSV",
                data=create_sample_file('csv'),
                file_name="sample_input.csv",
                mime="text/csv",
                key="sample-csv"
            )
        with col2:
            # Tombol untuk mendownload Excel contoh
            st.download_button(
                label="Download Sample Excel",
                data=create_sample_file('excel'),
                file_name="sample_input.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="sample-excel"
            )

    uploaded_file = st.file_uploader("Choose a file", type=['csv', 'xlsx'])
    if uploaded_file is not None:
        if uploaded_file.type == "text/csv":
            data = pd.read_csv(uploaded_file)
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            data = pd.read_excel(uploaded_file, engine='openpyxl')

        predictions = predict_bulk(model, tokenizer, label_encoder, data)
        predictions_df = pd.DataFrame(predictions, columns=['Emotion Prediction'])
        results = pd.concat([data, predictions_df], axis=1)
        
        st.write("Results with Predictions:")
        st.dataframe(results)

        # Setelah melakukan prediksi dan memiliki DataFrame `results`
        col1, col2 = st.columns([1, 2])
        with col1:
            # Tombol untuk mendownload hasil prediksi sebagai CSV
            st.download_button(
                label="Download Predictions as CSV",
                data=convert_df_to_csv(results),
                file_name='predictions.csv',
                mime='text/csv',
                key="predictions-csv"
            )
        with col2:
            # Tombol untuk mendownload hasil prediksi sebagai Excel
            st.download_button(
                label="Download Predictions as Excel",
                data=convert_df_to_excel(results),
                file_name='predictions.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key="predictions-excel"
            )