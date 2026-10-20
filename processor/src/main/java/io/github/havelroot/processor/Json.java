package io.github.havelroot.processor;

import com.google.gson.FieldNamingPolicy;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

/** JSON em snake_case, com nulos explícitos e sem escapar acentos ou "<" (a resposta não é HTML). */
public final class Json {

    private static final Gson GSON = new GsonBuilder()
            .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
            .serializeNulls()
            .disableHtmlEscaping()
            .create();

    private Json() {
    }

    public static String write(Object value) {
        return GSON.toJson(value);
    }

    public static JsonObject parseObject(String body) {
        try {
            JsonElement element = JsonParser.parseString(body);
            if (element == null || !element.isJsonObject()) {
                throw ProcessingException.badRequest("O corpo deve ser um objeto JSON");
            }
            return element.getAsJsonObject();
        } catch (JsonParseException | IllegalStateException e) {
            throw ProcessingException.badRequest("JSON inválido no corpo da requisição");
        }
    }
}
